"""ESP-IDF v6.1 Compatible NVS Partition Generator.

Generates standard NVS CSV descriptors and synthesizes binary partition images
containing the `nvs_sec` namespace with:
  - `device_mac`: 6-byte binary MAC (from 12-hex string)
  - `k_join`: 32-byte binary root pre-shared key (from 64-hex string)
  - `join_counter`: 32-bit unsigned integer (monotonic flash counter, default 0)
  - `k_beacon`: 32-byte binary beacon authentication key (from 64-hex string)

Supports both built-in pure-Python synthesis and invoking external
`nvs_partition_gen.py` from ESP-IDF toolchain.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from typing import Optional
import zlib


HEX_MAC_PATTERN = re.compile(r"^[0-9a-fA-F]{12}$")
HEX_KEY_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
GATEWAY_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,30}$")
MAX_GATEWAY_PEM_BYTES = 4095  # Leaves room for trailing NUL within 4096B firmware buffer

PAGE_SIZE = 4096
DEFAULT_PARTITION_SIZE = 0x6000  # 24KB (6 pages)

# NVS v2 Constants (per ESP-IDF nvs_partition_gen.py)
PAGE_STATE_ACTIVE = 0xFFFFFFFE
PAGE_STATE_FULL = 0xFFFFFFFC
NVS_VERSION_V2 = 0xFE
HEADER_SIZE = 32
BITMAP_SIZE = 32
ENTRY_SIZE = 32
MAX_ENTRIES_PER_PAGE = 126

# NVS Data Types
ITEM_TYPE_U8 = 0x01
ITEM_TYPE_U32 = 0x04
ITEM_TYPE_SZ = 0x21
ITEM_TYPE_BLOB = 0x41
ITEM_TYPE_BLOB_DATA = 0x42
ITEM_TYPE_BLOB_IDX = 0x48

CHUNK_ANY = 0xFF


def validate_mac(mac: str) -> str:
    """Validate and normalize a 12-character hex MAC address."""
    clean_mac = mac.strip().replace(":", "").replace("-", "").replace(" ", "").lower()
    if not HEX_MAC_PATTERN.fullmatch(clean_mac):
        raise ValueError(f"Invalid MAC address: '{mac}'. Expected 12 hexadecimal characters.")
    return clean_mac


def validate_key(key_hex: str, key_name: str = "key") -> str:
    """Validate and normalize a 64-character hex key (32 bytes)."""
    clean_key = key_hex.strip().lower()
    if not HEX_KEY_PATTERN.fullmatch(clean_key):
        raise ValueError(
            f"Invalid {key_name}: length {len(clean_key)} hex chars. Expected 64 hexadecimal characters (32 bytes)."
        )
    return clean_key


def validate_gateway_id(gateway_id: str) -> str:
    """Validate canonical Gateway ID matching Mosquitto ACL & Kconfig (1..31 chars)."""
    clean_id = gateway_id.strip()
    if not GATEWAY_ID_PATTERN.fullmatch(clean_id):
        raise ValueError(
            f"Invalid gateway_id '{gateway_id}'. Expected 1..31 chars matching [a-zA-Z0-9][a-zA-Z0-9_-]*."
        )
    return clean_id


def validate_pem_bytes(pem_data: bytes | bytearray, label: str, is_private_key: bool = False) -> bytes:
    """Validate non-empty PEM certificate or private key bytes and return normalized UTF-8 bytes."""
    if not isinstance(pem_data, (bytes, bytearray)) or len(pem_data) == 0:
        raise ValueError(f"{label} PEM data is empty")
    try:
        text = bytes(pem_data).decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} PEM is not valid UTF-8") from exc

    stripped = text.strip("\x00\r\n ")
    if not stripped:
        raise ValueError(f"{label} PEM is empty")
    if not stripped.endswith("\n"):
        stripped += "\n"

    begin_prefix = "-----BEGIN "
    end_prefix = "-----END "
    expected_suffix = ("PRIVATE " + "KEY-----") if is_private_key else "CERTIFICATE-----"

    begin_idx = stripped.find(begin_prefix)
    if begin_idx < 0:
        raise ValueError(f"{label} missing PEM BEGIN header")
    begin_line_end = stripped.find("\n", begin_idx)
    if begin_line_end < 0 or expected_suffix not in stripped[begin_idx:begin_line_end]:
        raise ValueError(f"{label} missing expected PEM header '{expected_suffix}'")

    end_idx = stripped.find(end_prefix, begin_line_end + 1)
    if end_idx < 0:
        raise ValueError(f"{label} missing PEM END footer")
    end_line = stripped[end_idx:].splitlines()[0]
    if expected_suffix not in end_line:
        raise ValueError(f"{label} missing expected PEM footer '{expected_suffix}'")

    body = stripped[begin_line_end + 1 : end_idx].strip()
    if not body:
        raise ValueError(f"{label} PEM body is empty")

    encoded = stripped.encode("utf-8")
    if len(encoded) > MAX_GATEWAY_PEM_BYTES:
        raise ValueError(
            f"{label} PEM length {len(encoded)} bytes exceeds max {MAX_GATEWAY_PEM_BYTES} bytes"
        )
    return encoded


def generate_nvs_csv(
    device_mac: str,
    k_join_hex: str,
    join_counter: int = 0,
    k_beacon_hex: Optional[str] = None,
) -> str:
    """Generate standard ESP-IDF NVS CSV descriptor string.

    Format matches esp-idf nvs_partition_gen requirements:
      key,type,encoding,value
    """
    clean_mac = validate_mac(device_mac)
    clean_k_join = validate_key(k_join_hex, "k_join")
    clean_k_beacon = validate_key(k_beacon_hex, "k_beacon") if k_beacon_hex else "00" * 32

    if not (0 <= join_counter <= 4294967295):
        raise ValueError(f"join_counter must be between 0 and 4294967295, got {join_counter}")

    lines = [
        "key,type,encoding,value",
        "nvs_sec,namespace,,",
        f"device_mac,data,hex2bin,{clean_mac}",
        f"k_join,data,hex2bin,{clean_k_join}",
        f"join_counter,data,u32,{join_counter}",
        f"k_beacon,data,hex2bin,{clean_k_beacon}",
        "",
    ]
    return "\n".join(lines)


class NVSV2PartitionWriter:
    """Pure-Python ESP-IDF v6.1 NVS partition binary synthesizer.

    Produces byte-exact V2 multipage-blob-compatible NVS binary partitions.
    """

    def __init__(self, partition_size: int = DEFAULT_PARTITION_SIZE):
        if partition_size % PAGE_SIZE != 0:
            raise ValueError(
                f"Partition size must be a multiple of {PAGE_SIZE} (0x1000) bytes, got {partition_size}"
            )
        if partition_size < 3 * PAGE_SIZE:
            raise ValueError(
                f"Partition size must be at least 3 pages ({3 * PAGE_SIZE} bytes), got {partition_size}"
            )
        self.partition_size = partition_size
        self.num_pages = partition_size // PAGE_SIZE

    @staticmethod
    def _crc32(data: bytes) -> int:
        return zlib.crc32(data, 0xFFFFFFFF) & 0xFFFFFFFF

    @staticmethod
    def _pack_entry_header(
        ns_index: int,
        entry_type: int,
        span: int,
        chunk_index: int,
        key: str,
        data_8b: bytes,
    ) -> bytes:
        """Pack standard 32-byte NVS item entry header with CRC32."""
        buf = bytearray(b"\xff" * ENTRY_SIZE)
        buf[0] = ns_index & 0xFF
        buf[1] = entry_type & 0xFF
        buf[2] = span & 0xFF
        buf[3] = chunk_index & 0xFF

        key_bytes = key.encode("utf-8")[:15]
        buf[8 : 8 + len(key_bytes)] = key_bytes
        buf[8 + len(key_bytes) : 24] = b"\x00" * (16 - len(key_bytes))
        buf[24:32] = data_8b[:8]

        crc_input = bytes(buf[0:4] + buf[8:32])
        crc = NVSV2PartitionWriter._crc32(crc_input)
        struct.pack_into("<I", buf, 4, crc)
        return bytes(buf)

    def synthesize_credentials_partition(
        self,
        device_mac: str,
        k_join_hex: str,
        join_counter: int = 0,
        k_beacon_hex: Optional[str] = None,
    ) -> bytes:
        """Synthesize complete NVS binary partition image containing credentials."""
        clean_mac = validate_mac(device_mac)
        clean_k_join = validate_key(k_join_hex, "k_join")
        clean_k_beacon = validate_key(k_beacon_hex, "k_beacon") if k_beacon_hex else "00" * 32

        mac_bytes = bytes.fromhex(clean_mac)
        k_join_bytes = bytes.fromhex(clean_k_join)
        k_beacon_bytes = bytes.fromhex(clean_k_beacon)

        page0 = bytearray(b"\xff" * PAGE_SIZE)

        # 1. Page 0 Header (32 bytes)
        # Format: state (4B), seq_num (4B), version (1B), 19B padding (0xFF), crc32 (4B)
        page_header = bytearray(b"\xff" * HEADER_SIZE)
        struct.pack_into("<I", page_header, 0, PAGE_STATE_ACTIVE)
        struct.pack_into("<I", page_header, 4, 0)  # seq_num = 0
        page_header[8] = NVS_VERSION_V2
        header_crc = self._crc32(bytes(page_header[4:28]))
        struct.pack_into("<I", page_header, 28, header_crc)
        page0[0:HEADER_SIZE] = page_header

        # Entries buffer
        entries: list[bytes] = []

        # Entry 0: Namespace 'nvs_sec' (ns_index=0, type=U8, span=1, chunk=0xFF, value=1)
        ns_data = bytes([1]) + (b"\xff" * 7)
        entries.append(
            self._pack_entry_header(
                ns_index=0,
                entry_type=ITEM_TYPE_U8,
                span=1,
                chunk_index=CHUNK_ANY,
                key="nvs_sec",
                data_8b=ns_data,
            )
        )

        # Helper for adding V2 blob entries (BLOB_DATA + data + BLOB_IDX)
        def add_v2_blob(key: str, data: bytes):
            data_len = len(data)
            rounded_len = (data_len + 31) & ~31
            entry_count = rounded_len // ENTRY_SIZE
            span = entry_count + 1

            # BLOB_DATA Header
            data_crc = self._crc32(data)
            blob_data_header_bytes = bytearray(b"\xff" * 8)
            struct.pack_into("<H", blob_data_header_bytes, 0, data_len)
            struct.pack_into("<I", blob_data_header_bytes, 4, data_crc)
            entries.append(
                self._pack_entry_header(
                    ns_index=1,
                    entry_type=ITEM_TYPE_BLOB_DATA,
                    span=span,
                    chunk_index=0,
                    key=key,
                    data_8b=bytes(blob_data_header_bytes),
                )
            )

            # Data Chunk (padded to 32B)
            padded_data = bytearray(data)
            if len(padded_data) < rounded_len:
                padded_data.extend(b"\xff" * (rounded_len - len(padded_data)))
            for i in range(0, rounded_len, ENTRY_SIZE):
                entries.append(bytes(padded_data[i : i + ENTRY_SIZE]))

            # BLOB_IDX Header
            blob_idx_bytes = bytearray(b"\xff" * 8)
            struct.pack_into("<I", blob_idx_bytes, 0, data_len)
            blob_idx_bytes[4] = 1  # chunk_count = 1
            blob_idx_bytes[5] = 0  # chunk_start = 0
            entries.append(
                self._pack_entry_header(
                    ns_index=1,
                    entry_type=ITEM_TYPE_BLOB_IDX,
                    span=1,
                    chunk_index=CHUNK_ANY,
                    key=key,
                    data_8b=bytes(blob_idx_bytes),
                )
            )

        # Entry 1..3: device_mac (6B)
        add_v2_blob("device_mac", mac_bytes)

        # Entry 4..6: k_join (32B)
        add_v2_blob("k_join", k_join_bytes)

        # Entry 7: join_counter (u32 primitive)
        jc_data = bytearray(b"\xff" * 8)
        struct.pack_into("<I", jc_data, 0, join_counter)
        entries.append(
            self._pack_entry_header(
                ns_index=1,
                entry_type=ITEM_TYPE_U32,
                span=1,
                chunk_index=CHUNK_ANY,
                key="join_counter",
                data_8b=bytes(jc_data),
            )
        )

        # Entry 8..10: k_beacon (32B)
        add_v2_blob("k_beacon", k_beacon_bytes)

        # Total entry slots in Page 0
        total_slots = len(entries)
        if total_slots > MAX_ENTRIES_PER_PAGE:
            raise RuntimeError(f"Entries count {total_slots} exceeds page capacity {MAX_ENTRIES_PER_PAGE}")

        # 2. Build Bitmap Array (32 bytes = 256 bits, 2 bits per entry slot)
        # Unwritten = 0b11, Written/Active = 0b10 (bit offset has 0 in lower bit)
        bitmap = bytearray([0xFF] * BITMAP_SIZE)
        for slot in range(total_slots):
            bitnum = slot * 2
            byte_idx = bitnum // 8
            bit_offset = bitnum & 7
            mask = ~(1 << bit_offset)
            bitmap[byte_idx] &= mask

        page0[HEADER_SIZE : HEADER_SIZE + BITMAP_SIZE] = bitmap

        # 3. Write Entries into Page 0
        data_offset = HEADER_SIZE + BITMAP_SIZE
        for entry in entries:
            page0[data_offset : data_offset + len(entry)] = entry
            data_offset += len(entry)

        # 4. Assemble Entire Partition Image (Page 0 + empty Pages 1..N-1)
        partition = bytearray(b"\xff" * self.partition_size)
        partition[0:PAGE_SIZE] = page0

        return bytes(partition)

    def _build_page_header(self, seq_num: int, state: int = PAGE_STATE_ACTIVE) -> bytes:
        page_header = bytearray(b"\xff" * HEADER_SIZE)
        struct.pack_into("<I", page_header, 0, state)
        struct.pack_into("<I", page_header, 4, seq_num)
        page_header[8] = NVS_VERSION_V2
        header_crc = self._crc32(bytes(page_header[4:28]))
        struct.pack_into("<I", page_header, 28, header_crc)
        return bytes(page_header)

    @staticmethod
    def _finalize_page(seq_num: int, entries: list[bytes], page_header: bytes) -> bytes:
        page = bytearray(b"\xff" * PAGE_SIZE)
        page[0:HEADER_SIZE] = page_header
        bitmap = bytearray([0xFF] * BITMAP_SIZE)
        for slot in range(len(entries)):
            bitnum = slot * 2
            byte_idx = bitnum // 8
            bit_offset = bitnum & 7
            bitmap[byte_idx] &= ~(1 << bit_offset)
        page[HEADER_SIZE : HEADER_SIZE + BITMAP_SIZE] = bitmap
        data_offset = HEADER_SIZE + BITMAP_SIZE
        for entry in entries:
            page[data_offset : data_offset + ENTRY_SIZE] = entry
            data_offset += ENTRY_SIZE
        return bytes(page)

    def synthesize_gateway_tls_partition(
        self,
        gateway_id: str,
        ca_cert_pem: bytes,
        client_cert_pem: bytes,
        client_key_pem: bytes | bytearray,
    ) -> bytes:
        """Synthesize multi-page ESP-IDF v6.1 NVS partition for Gateway mTLS credentials."""
        clean_gw_id = validate_gateway_id(gateway_id)
        ca_bytes = validate_pem_bytes(ca_cert_pem, "ca_cert", is_private_key=False) + b"\x00"
        cert_bytes = validate_pem_bytes(client_cert_pem, "client_cert", is_private_key=False) + b"\x00"
        key_bytes = validate_pem_bytes(client_key_pem, "client_key", is_private_key=True) + b"\x00"
        gw_id_bytes = clean_gw_id.encode("utf-8") + b"\x00"

        pages: list[bytes] = []
        cur_entries: list[bytes] = []
        seq_num = 0

        def flush_page():
            nonlocal cur_entries, seq_num
            pages.append(
                self._finalize_page(
                    seq_num,
                    cur_entries,
                    self._build_page_header(seq_num, state=PAGE_STATE_FULL),
                )
            )
            cur_entries = []
            seq_num += 1
            # Reserve at least 1 spare erased page for ESP-IDF NVS wear-leveling
            if seq_num >= self.num_pages - 1:
                raise RuntimeError(
                    f"NVS partition size 0x{self.partition_size:x} too small (needs >= 1 spare page)"
                )

        # Entry 0: Namespace 'nvs_tls' (ns_index=0, type=U8, span=1, chunk=0xFF, value=1)
        ns_data = bytes([1]) + (b"\xff" * 7)
        cur_entries.append(
            self._pack_entry_header(
                ns_index=0,
                entry_type=ITEM_TYPE_U8,
                span=1,
                chunk_index=CHUNK_ANY,
                key="nvs_tls",
                data_8b=ns_data,
            )
        )

        def add_multipage_blob(key: str, data: bytes):
            data_size = len(data)
            remaining_size = data_size
            offset = 0
            chunk_count = 0

            while remaining_size > 0:
                if (MAX_ENTRIES_PER_PAGE - len(cur_entries)) < 2:
                    flush_page()

                tailroom = (MAX_ENTRIES_PER_PAGE - len(cur_entries) - 1) * ENTRY_SIZE
                chunk_size = min(remaining_size, tailroom)
                remaining_size -= chunk_size

                rounded_len = (chunk_size + 31) & ~31
                data_entry_count = rounded_len // ENTRY_SIZE
                span = data_entry_count + 1

                chunk = data[offset : offset + chunk_size]
                data_crc = self._crc32(chunk)
                hdr_data = bytearray(b"\xff" * 8)
                struct.pack_into("<H", hdr_data, 0, chunk_size)
                struct.pack_into("<I", hdr_data, 4, data_crc)
                cur_entries.append(
                    self._pack_entry_header(
                        ns_index=1,
                        entry_type=ITEM_TYPE_BLOB_DATA,
                        span=span,
                        chunk_index=chunk_count,
                        key=key,
                        data_8b=bytes(hdr_data),
                    )
                )

                padded = bytearray(chunk)
                if len(padded) < rounded_len:
                    padded.extend(b"\xff" * (rounded_len - len(padded)))
                for i in range(0, rounded_len, ENTRY_SIZE):
                    cur_entries.append(bytes(padded[i : i + ENTRY_SIZE]))

                chunk_count += 1
                offset += chunk_size

                if remaining_size > 0 or (tailroom - chunk_size) < ENTRY_SIZE:
                    flush_page()

            idx_data = bytearray(b"\xff" * 8)
            struct.pack_into("<I", idx_data, 0, data_size)
            idx_data[4] = chunk_count
            idx_data[5] = 0
            cur_entries.append(
                self._pack_entry_header(
                    ns_index=1,
                    entry_type=ITEM_TYPE_BLOB_IDX,
                    span=1,
                    chunk_index=CHUNK_ANY,
                    key=key,
                    data_8b=bytes(idx_data),
                )
            )

        add_multipage_blob("gateway_id", gw_id_bytes)
        add_multipage_blob("ca_cert", ca_bytes)
        add_multipage_blob("client_cert", cert_bytes)
        add_multipage_blob("client_key", key_bytes)

        if cur_entries:
            if len(pages) >= self.num_pages - 1:
                raise RuntimeError(
                    f"NVS partition size 0x{self.partition_size:x} too small (needs >= 1 spare page)"
                )
            pages.append(
                self._finalize_page(
                    seq_num,
                    cur_entries,
                    self._build_page_header(seq_num, state=PAGE_STATE_ACTIVE),
                )
            )
        elif pages:
            # Mark the last written page ACTIVE if flushing happened right on entry boundary
            last = bytearray(pages[-1])
            struct.pack_into("<I", last, 0, PAGE_STATE_ACTIVE)
            pages[-1] = bytes(last)

        partition = bytearray(b"\xff" * self.partition_size)
        for idx, page_bytes in enumerate(pages):
            start = idx * PAGE_SIZE
            partition[start : start + PAGE_SIZE] = page_bytes
        return bytes(partition)


def find_esp_idf_nvs_gen_tool() -> Optional[str]:
    """Find path to external esp-idf nvs_partition_gen.py if installed."""
    # Check PATH
    which_path = shutil.which("nvs_partition_gen.py")
    if which_path:
        return which_path

    # Check IDF_PATH environment variable
    idf_path = os.environ.get("IDF_PATH")
    if idf_path:
        candidate = Path(idf_path) / "components" / "nvs_flash" / "nvs_partition_generator" / "nvs_partition_gen.py"
        if candidate.is_file():
            return str(candidate)

    # Check common ~/.espressif python envs
    home_espressif = Path.home() / ".espressif" / "python_env"
    if home_espressif.is_dir():
        for env_dir in home_espressif.iterdir():
            candidate_bin = env_dir / "bin" / "python3"
            if candidate_bin.is_file():
                # Test if esp_idf_nvs_partition_gen is importable
                try:
                    result = subprocess.run(
                        [str(candidate_bin), "-c", "import esp_idf_nvs_partition_gen"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                        check=False,
                    )
                    if result.returncode == 0:
                        return f"{candidate_bin} -m esp_idf_nvs_partition_gen.nvs_partition_gen"
                except (OSError, subprocess.SubprocessError):
                    pass

    return None


def synthesize_nvs_partition(
    device_mac: str,
    k_join_hex: str,
    join_counter: int = 0,
    k_beacon_hex: Optional[str] = None,
    partition_size: int = DEFAULT_PARTITION_SIZE,
    output_bin: Optional[Path] = None,
    output_csv: Optional[Path] = None,
    use_external_tool: bool = False,
    nvs_tool_path: Optional[str] = None,
) -> bytes:
    """High-level function to synthesize NVS credentials partition image.

    Writes CSV and bin files to disk if requested and returns raw binary bytes.
    """
    clean_mac = validate_mac(device_mac)
    clean_k_join = validate_key(k_join_hex, "k_join")
    clean_k_beacon = validate_key(k_beacon_hex, "k_beacon") if k_beacon_hex else "00" * 32

    csv_content = generate_nvs_csv(
        device_mac=clean_mac,
        k_join_hex=clean_k_join,
        join_counter=join_counter,
        k_beacon_hex=clean_k_beacon,
    )

    if output_csv:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        output_csv.write_text(csv_content, encoding="utf-8")

    tool_used = False
    if use_external_tool:
        tool_cmd = nvs_tool_path or find_esp_idf_nvs_gen_tool()
        if tool_cmd:
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_csv = Path(tmpdir) / "credentials.csv"
                tmp_bin = Path(tmpdir) / "credentials.bin"
                tmp_csv.write_text(csv_content, encoding="utf-8")

                if " -m " in tool_cmd:
                    python_exe, mod_part = tool_cmd.split(" -m ", 1)
                    cmd = [python_exe, "-m", mod_part, "generate", str(tmp_csv), str(tmp_bin), hex(partition_size)]
                else:
                    cmd = [sys.executable, tool_cmd, "generate", str(tmp_csv), str(tmp_bin), hex(partition_size)]

                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
                if proc.returncode == 0 and tmp_bin.is_file():
                    bin_data = tmp_bin.read_bytes()
                    tool_used = True
                    if output_bin:
                        output_bin.parent.mkdir(parents=True, exist_ok=True)
                        output_bin.write_bytes(bin_data)
                    return bin_data

    # Fallback to pure-Python synthesizer (default and fully compatible)
    writer = NVSV2PartitionWriter(partition_size=partition_size)
    bin_data = writer.synthesize_credentials_partition(
        device_mac=clean_mac,
        k_join_hex=clean_k_join,
        join_counter=join_counter,
        k_beacon_hex=clean_k_beacon,
    )

    if output_bin:
        output_bin.parent.mkdir(parents=True, exist_ok=True)
        output_bin.write_bytes(bin_data)

    return bin_data


def generate_gateway_tls_csv(
    gateway_id: str,
    ca_cert_path: Path,
    client_cert_path: Path,
    client_key_path: Path,
) -> str:
    """Generate ESP-IDF nvs_partition_gen CSV descriptor for nvs_tls namespace."""
    clean_gw_id = validate_gateway_id(gateway_id)
    gw_hex = (clean_gw_id.encode("utf-8") + b"\x00").hex()
    ca_hex = (validate_pem_bytes(ca_cert_path.read_bytes(), "ca_cert", is_private_key=False) + b"\x00").hex()
    cert_hex = (
        validate_pem_bytes(client_cert_path.read_bytes(), "client_cert", is_private_key=False) + b"\x00"
    ).hex()
    key_hex = (
        validate_pem_bytes(client_key_path.read_bytes(), "client_key", is_private_key=True) + b"\x00"
    ).hex()

    lines = [
        "key,type,encoding,value",
        "nvs_tls,namespace,,",
        f"gateway_id,data,hex2bin,{gw_hex}",
        f"ca_cert,data,hex2bin,{ca_hex}",
        f"client_cert,data,hex2bin,{cert_hex}",
        f"client_key,data,hex2bin,{key_hex}",
        "",
    ]
    return "\n".join(lines)


def synthesize_gateway_tls_partition(
    gateway_id: str,
    ca_cert_pem: bytes,
    client_cert_pem: bytes,
    client_key_pem: bytes | bytearray,
    partition_size: int = DEFAULT_PARTITION_SIZE,
    output_bin: Optional[Path] = None,
    use_external_tool: bool = False,
    nvs_tool_path: Optional[str] = None,
) -> bytes:
    """Synthesize ESP-IDF v6.1 NVS partition image with Gateway mTLS credentials."""
    clean_gw_id = validate_gateway_id(gateway_id)
    ca_bytes = validate_pem_bytes(ca_cert_pem, "ca_cert", is_private_key=False)
    cert_bytes = validate_pem_bytes(client_cert_pem, "client_cert", is_private_key=False)
    key_bytes = validate_pem_bytes(client_key_pem, "client_key", is_private_key=True)

    if use_external_tool:
        tool_cmd = nvs_tool_path or find_esp_idf_nvs_gen_tool()
        if tool_cmd:
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_dir = Path(tmpdir)
                tmp_csv = tmp_dir / "nvs_tls.csv"
                tmp_bin = tmp_dir / "nvs_tls.bin"
                ca_p = tmp_dir / "ca.bin"
                cert_p = tmp_dir / "cert.bin"
                key_p = tmp_dir / "key.bin"
                gw_p = tmp_dir / "gw.bin"
                gw_p.write_bytes(clean_gw_id.encode("utf-8") + b"\x00")
                ca_p.write_bytes(ca_bytes + b"\x00")
                cert_p.write_bytes(cert_bytes + b"\x00")
                key_p.write_bytes(key_bytes + b"\x00")
                os.chmod(key_p, 0o600)

                csv_lines = [
                    "key,type,encoding,value",
                    "nvs_tls,namespace,,",
                    f"gateway_id,file,binary,{gw_p}",
                    f"ca_cert,file,binary,{ca_p}",
                    f"client_cert,file,binary,{cert_p}",
                    f"client_key,file,binary,{key_p}",
                    "",
                ]
                tmp_csv.write_text("\n".join(csv_lines), encoding="utf-8")

                if " -m " in tool_cmd:
                    python_exe, mod_part = tool_cmd.split(" -m ", 1)
                    cmd = [python_exe, "-m", mod_part, "generate", str(tmp_csv), str(tmp_bin), hex(partition_size)]
                else:
                    cmd = [sys.executable, tool_cmd, "generate", str(tmp_csv), str(tmp_bin), hex(partition_size)]

                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
                if proc.returncode == 0 and tmp_bin.is_file():
                    bin_data = tmp_bin.read_bytes()
                    if output_bin:
                        output_bin.parent.mkdir(parents=True, exist_ok=True)
                        output_bin.write_bytes(bin_data)
                        os.chmod(output_bin, 0o600)
                    return bin_data

    writer = NVSV2PartitionWriter(partition_size=partition_size)
    bin_data = writer.synthesize_gateway_tls_partition(
        gateway_id=clean_gw_id,
        ca_cert_pem=ca_bytes,
        client_cert_pem=cert_bytes,
        client_key_pem=key_bytes,
    )

    if output_bin:
        output_bin.parent.mkdir(parents=True, exist_ok=True)
        output_bin.write_bytes(bin_data)
        os.chmod(output_bin, 0o600)

    return bin_data
