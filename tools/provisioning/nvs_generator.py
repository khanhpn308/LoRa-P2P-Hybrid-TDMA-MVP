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

PAGE_SIZE = 4096
DEFAULT_PARTITION_SIZE = 0x6000  # 24KB (6 pages)

# NVS v2 Constants (per ESP-IDF nvs_partition_gen.py)
PAGE_STATE_ACTIVE = 0xFFFFFFFE
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
