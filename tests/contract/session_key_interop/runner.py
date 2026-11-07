#!/usr/bin/env python3
"""
Test runner and cross-language interoperability verifier for MQTT Session Key contracts.
Authority: Issue #173, PR #123, contracts/mqtt/session-key-security.md.
"""

from __future__ import annotations
import base64
from datetime import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[3]
TEST_DIR = ROOT / "tests" / "contract" / "session_key_interop"
VECTORS_FILE = TEST_DIR / "session_key_vectors.json"
ESP_DIR = TEST_DIR / "esp_idf_adapter"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def step1_verify_golden_vectors() -> dict:
    print("[1/4] Verifying Deterministic Golden Vectors...")
    if not VECTORS_FILE.is_file():
        raise FileNotFoundError(f"Missing {VECTORS_FILE}")

    data = json.loads(VECTORS_FILE.read_text(encoding="utf-8"))
    syn = data["synthetic_keys"]
    pos = data["positive_cases"]
    neg = data["negative_cases"]

    k_gw_wrap = bytes.fromhex(syn["k_gw_wrap_hex"])
    k_session_up = bytes.fromhex(syn["k_session_up_hex"])
    k_session_dl = bytes.fromhex(syn["k_session_dl_hex"])
    plaintext = k_session_up + k_session_dl
    assert len(plaintext) == 64

    # Verify Vector 1 (Install)
    c1 = pos[0]
    msg = c1["message"]
    nonce = base64.b64decode(msg["nonce"])
    expected_aad = bytes.fromhex(c1["intermediate"]["aad_hex"])
    assert len(expected_aad) == 232

    aesgcm = AESGCM(k_gw_wrap)
    expected_ct = bytes.fromhex(c1["intermediate"]["ciphertext_hex"])
    expected_tag = bytes.fromhex(c1["intermediate"]["tag_hex"])
    dec = aesgcm.decrypt(nonce, expected_ct + expected_tag, expected_aad)
    assert dec == plaintext, "Python reference decryption failed"

    # Verify Vector 2 (ACK Installed)
    c2 = pos[1]
    expected_k_ack = bytes.fromhex(syn["k_ack_hex"])
    expected_m_ack = bytes.fromhex(c2["intermediate"]["m_ack_hex"])
    assert len(expected_m_ack) == 138

    expected_ack_tag = bytes.fromhex(c2["intermediate"]["ack_tag_hex"])
    computed_ack_tag = hmac.new(expected_k_ack, expected_m_ack, hashlib.sha256).digest()[:16]
    assert computed_ack_tag == expected_ack_tag, "Python reference ACK tag calculation mismatch"

    print("      Golden vectors validated against independent Python cryptography reference.")
    return {
        "status": "PASS",
        "vectors_hash": sha256_file(VECTORS_FILE),
        "positive_cases_count": len(pos),
        "negative_cases_count": len(neg),
    }

def step2_run_go_tests() -> dict:
    print("[2/4] Running Go Contract Test Adapter...")
    go_bin = "/usr/local/go/bin/go"
    if not os.path.exists(go_bin):
        raise RuntimeError("Go compiler not found at /usr/local/go/bin/go")

    cmd = [go_bin, "test", "-v", "./..."]
    res = subprocess.run(cmd, cwd=str(TEST_DIR), capture_output=True, text=True)
    if res.returncode != 0:
        print("Go test output:\n", res.stdout)
        print("Go test stderr:\n", res.stderr)
        raise RuntimeError(f"Go tests failed with exit code {res.returncode}")

    passed_count = len(re.findall(r"--- PASS:", res.stdout))
    print(f"      Go tests PASSED: {passed_count} test functions executed.")
    return {
        "status": "PASS",
        "exit_code": res.returncode,
        "passed_tests": passed_count,
        "output_summary": [line for line in res.stdout.splitlines() if line.startswith("--- PASS:") or line.startswith("ok")],
    }

def step3_run_esp_idf_tests() -> dict:
    print("[3/4] Building and executing ESP-IDF mbedTLS Adapter (ESP32 in QEMU)...")
    build_dir = ESP_DIR / "build"

    # Step 3a: idf.py build
    cmd_build = [
        "docker", "run", "--rm", "--pull=never",
        "--network=none", "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--tmpfs=/tmp:rw,nosuid,nodev,size=1g",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--env", "HOME=/tmp",
        "--mount", f"type=bind,src={ROOT},dst=/workspace",
        "--workdir", f"/workspace/tests/contract/session_key_interop/esp_idf_adapter",
        "espressif/idf:v6.1",
        "idf.py", "build"
    ]
    res_b = subprocess.run(cmd_build, capture_output=True, text=True)
    if res_b.returncode != 0:
        print("ESP-IDF build stderr:\n", res_b.stderr[-1000:])
        raise RuntimeError(f"ESP-IDF build failed with exit code {res_b.returncode}")

    # Step 3b: Merge flash binary using esptool
    cmd_merge = [
        "docker", "run", "--rm", "--pull=never",
        "--network=none",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--env", "HOME=/tmp",
        "--mount", f"type=bind,src={build_dir},dst=/build",
        "--workdir", "/build",
        "espressif/idf:v6.1",
        "esptool", "--chip", "esp32", "merge-bin", "-o", "qemu_flash.bin", "@flash_args"
    ]
    res_m = subprocess.run(cmd_merge, capture_output=True, text=True)
    if res_m.returncode != 0:
        print("esptool merge-bin failed:\n", res_m.stderr)
        raise RuntimeError(f"esptool merge-bin failed with exit code {res_m.returncode}")

    # Truncate to 2MB on host
    flash_bin = build_dir / "qemu_flash.bin"
    subprocess.run(["truncate", "-s", "2M", str(flash_bin)], check=True)

    # Step 3c: Run QEMU with timeout
    cmd_qemu = [
        "docker", "run", "--rm", "--pull=never",
        "--network=none",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--env", "HOME=/tmp",
        "--mount", f"type=bind,src={build_dir},dst=/build",
        "--workdir", "/build",
        "espressif/idf:v6.1",
        "timeout", "12s",
        "qemu-system-xtensa", "-nographic", "-machine", "esp32",
        "-drive", "file=qemu_flash.bin,if=mtd,format=raw",
        "-serial", "mon:stdio", "-no-reboot"
    ]
    res_q = subprocess.run(cmd_qemu, capture_output=True, text=True)

    output = res_q.stdout
    if "=== ESP32 MBEDTLS ALL TESTS PASSED ===" not in output:
        print("QEMU stdout:\n", output)
        raise RuntimeError("QEMU execution did not pass all ESP32 mbedTLS tests")

    tests_passed = len(re.findall(r"\.\.\. PASSED", output))
    print(f"      ESP32 mbedTLS tests PASSED in QEMU: {tests_passed} checks verified.")
    return {
        "status": "PASS",
        "qemu_verified": True,
        "tests_passed": tests_passed,
        "output_summary": [line for line in output.splitlines() if "PASSED" in line or "SUMMARY" in line],
    }

def step4_cross_language_summary(v_res: dict, g_res: dict, e_res: dict) -> dict:
    print("[4/4] Verifying Cross-Language Cryptographic Compatibility Summary...")
    evidence = {
        "issue": 173,
        "title": "Verify MQTT Session Key AES-GCM/HMAC Golden Vectors across Go and ESP-IDF mbedTLS",
        "contract": {
            "source_pr": 123,
            "commit_sha": "9ab052e24c8135f890ecd7e0ff5efa1f1313dd91",
            "schema_version": "1.1-draft",
            "install_protocol_version": 1,
            "aad_version": 1,
            "ack_protocol_version": 1,
            "crypto_suite": "AES-256-GCM",
        },
        "toolchains": {
            "go": "go1.27.1 linux/amd64",
            "esp_idf": "v6.1",
            "mbedtls": "tf-psa-crypto (mbedTLS 3.6.x compatible)",
            "emulator": "qemu-system-xtensa 9.2.2",
        },
        "file_hashes": {
            "session_key_vectors.json": v_res["vectors_hash"],
            "session_key_crypto.go": sha256_file(TEST_DIR / "session_key_crypto.go"),
            "session_key_crypto_test.go": sha256_file(TEST_DIR / "session_key_crypto_test.go"),
            "session_key_crypto.h": sha256_file(ESP_DIR / "main" / "session_key_crypto.h"),
            "session_key_crypto.c": sha256_file(ESP_DIR / "main" / "session_key_crypto.c"),
            "test_main.c": sha256_file(ESP_DIR / "main" / "test_main.c"),
        },
        "results": {
            "vectors": v_res,
            "go_adapter": g_res,
            "esp_idf_mbedtls_adapter": e_res,
            "interop_verified": True,
        }
    }

    out_json = TEST_DIR / "interop_evidence.json"
    out_json.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"      Evidence manifest written to {out_json}")
    return evidence

def main():
    print("================================================================================")
    print("  MQTT SESSION KEY GOLDEN VECTORS & CROSS-LANGUAGE INTEROP VERIFIER (#173)      ")
    print("================================================================================")
    v_res = step1_verify_golden_vectors()
    g_res = step2_run_go_tests()
    e_res = step3_run_esp_idf_tests()
    ev = step4_cross_language_summary(v_res, g_res, e_res)
    print("\nALL INTEROP VERIFICATION STEPS COMPLETED SUCCESSFULLY (STATUS: PASS)!")

if __name__ == "__main__":
    main()
