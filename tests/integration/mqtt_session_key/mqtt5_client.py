"""Deterministic, lightweight MQTT 5.0 client over mTLS.
Pure Python standard library (socket, ssl, struct, select). No external dependencies.
Authority: MQTT 5.0 OASIS Standard, ADR-0002, Issue #174.
"""

from __future__ import annotations

import select
import socket
import ssl
import struct
import time
from typing import Optional, Tuple, Dict, Any, List


def encode_var_int(val: int) -> bytes:
    """Encode an integer as an MQTT variable byte integer (1-4 bytes)."""
    if val < 0 or val > 268435455:
        raise ValueError(f"Varint out of range: {val}")
    buf = bytearray()
    while True:
        b = val % 128
        val //= 128
        if val > 0:
            b |= 0x80
        buf.append(b)
        if val == 0:
            break
    return bytes(buf)


def decode_var_int_from_stream(sock: socket.socket) -> int:
    """Decode an MQTT variable byte integer directly from socket."""
    multiplier = 1
    value = 0
    while True:
        b = sock.recv(1)
        if not b:
            raise ConnectionResetError("Connection closed while reading varint")
        byte_val = b[0]
        value += (byte_val & 127) * multiplier
        if (byte_val & 128) == 0:
            break
        multiplier *= 128
        if multiplier > 128 * 128 * 128:
            raise ValueError("Malformed variable byte integer")
    return value


def encode_str(s: str) -> bytes:
    """Encode UTF-8 string with 2-byte length prefix."""
    raw = s.encode("utf-8")
    return struct.pack("!H", len(raw)) + raw


def decode_str(data: bytes, offset: int) -> Tuple[str, int]:
    """Decode 2-byte length prefixed UTF-8 string."""
    length = struct.unpack_from("!H", data, offset)[0]
    offset += 2
    raw = data[offset : offset + length]
    return raw.decode("utf-8"), offset + length


class Mqtt5Client:
    """MQTT 5.0 client over mTLS."""

    def __init__(
        self,
        host: str,
        port: int,
        ca_cert_path: str,
        client_cert_path: Optional[str] = None,
        client_key_path: Optional[str] = None,
        server_hostname: str = "localhost",
    ):
        self.host = host
        self.port = port
        self.ca_cert_path = ca_cert_path
        self.client_cert_path = client_cert_path
        self.client_key_path = client_key_path
        self.server_hostname = server_hostname
        self.sock: Optional[ssl.SSLSocket] = None
        self._next_packet_id = 1

    def _get_packet_id(self) -> int:
        pid = self._next_packet_id
        self._next_packet_id = (self._next_packet_id % 65535) + 1
        return pid

    def connect_tls(self, timeout: float = 5.0) -> None:
        """Establish mTLS connection to broker."""
        context = ssl.create_default_context(cafile=self.ca_cert_path)
        if self.client_cert_path and self.client_key_path:
            context.load_cert_chain(self.client_cert_path, self.client_key_path)
        raw_sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock = context.wrap_socket(raw_sock, server_hostname=self.server_hostname)
        self.sock.settimeout(timeout)

    def connect_mqtt5(
        self,
        client_id: str,
        clean_start: bool = True,
        session_expiry_sec: Optional[int] = None,
        keep_alive: int = 60,
    ) -> int:
        """Send MQTT 5.0 CONNECT packet and receive CONNACK Reason Code."""
        if not self.sock:
            raise RuntimeError("TLS connection not established")

        # Variable header
        proto_name = encode_str("MQTT")
        proto_ver = b"\x05"
        connect_flags = 0x02 if clean_start else 0x00
        keep_alive_bytes = struct.pack("!H", keep_alive)

        # Properties
        props = bytearray()
        if session_expiry_sec is not None:
            # Property 0x11: Session Expiry Interval (4-byte integer)
            props.append(0x11)
            props.extend(struct.pack("!I", session_expiry_sec))
        props_encoded = encode_var_int(len(props)) + bytes(props)

        # Payload
        payload = encode_str(client_id)

        var_header = proto_name + proto_ver + bytes([connect_flags]) + keep_alive_bytes + props_encoded
        packet = b"\x10" + encode_var_int(len(var_header) + len(payload)) + var_header + payload
        self.sock.sendall(packet)

        # Read CONNACK (0x20)
        pkt_type_b = self.sock.recv(1)
        if not pkt_type_b:
            raise ConnectionResetError("Broker closed connection during CONNECT")
        pkt_type = pkt_type_b[0]
        if pkt_type != 0x20:
            raise ValueError(f"Expected CONNACK (0x20), got 0x{pkt_type:02x}")

        rem_len = decode_var_int_from_stream(self.sock)
        connack_data = bytearray()
        while len(connack_data) < rem_len:
            chunk = self.sock.recv(rem_len - len(connack_data))
            if not chunk:
                raise ConnectionResetError("Truncated CONNACK")
            connack_data.extend(chunk)

        conn_flags = connack_data[0]
        reason_code = connack_data[1]
        return reason_code

    def subscribe(self, topic: str, qos: int = 1) -> int:
        """Send SUBSCRIBE packet and return SUBACK Reason Code."""
        if not self.sock:
            raise RuntimeError("Not connected")

        packet_id = self._get_packet_id()
        var_header = struct.pack("!H", packet_id) + encode_var_int(0)  # No properties

        # Payload: Topic Filter + Options (QoS)
        payload = encode_str(topic) + bytes([qos & 0x03])

        packet = b"\x82" + encode_var_int(len(var_header) + len(payload)) + var_header + payload
        self.sock.sendall(packet)

        # Read SUBACK (0x90)
        pkt_type = self.sock.recv(1)[0]
        if pkt_type != 0x90:
            raise ValueError(f"Expected SUBACK (0x90), got 0x{pkt_type:02x}")

        rem_len = decode_var_int_from_stream(self.sock)
        suback_data = bytearray()
        while len(suback_data) < rem_len:
            chunk = self.sock.recv(rem_len - len(suback_data))
            if not chunk:
                raise ConnectionResetError("Truncated SUBACK")
            suback_data.extend(chunk)

        recv_pid = struct.unpack_from("!H", suback_data, 0)[0]
        # Skip properties
        prop_len_val = suback_data[2]
        # In simple cases prop len is 0; reason code starts at 3 + prop_len_val
        reason_code_idx = 3 + prop_len_val
        reason_code = suback_data[reason_code_idx]
        return reason_code

    def publish(
        self,
        topic: str,
        payload: bytes,
        qos: int = 1,
        retain: bool = False,
        message_expiry_sec: Optional[int] = None,
        dup: bool = False,
    ) -> int:
        """Publish message at QoS 1 and return PUBACK Reason Code."""
        if not self.sock:
            raise RuntimeError("Not connected")

        flags = 0
        if dup:
            flags |= 0x08
        flags |= (qos & 0x03) << 1
        if retain:
            flags |= 0x01
        first_byte = 0x30 | flags

        packet_id = self._get_packet_id()
        topic_bytes = encode_str(topic)
        var_header = topic_bytes + struct.pack("!H", packet_id)

        # Properties
        props = bytearray()
        if message_expiry_sec is not None:
            # Property 0x02: Message Expiry Interval
            props.append(0x02)
            props.extend(struct.pack("!I", message_expiry_sec))
        props_encoded = encode_var_int(len(props)) + bytes(props)
        var_header += props_encoded

        rem_len = len(var_header) + len(payload)
        packet = bytes([first_byte]) + encode_var_int(rem_len) + var_header + payload
        self.sock.sendall(packet)

        if qos == 0:
            return 0

        # Read PUBACK (0x40)
        pkt_type_b = self.sock.recv(1)
        if not pkt_type_b:
            raise ConnectionResetError("Broker closed connection while waiting for PUBACK")
        pkt_type = pkt_type_b[0]
        if (pkt_type & 0xF0) != 0x40:
            raise ValueError(f"Expected PUBACK (0x40), got 0x{pkt_type:02x}")

        rem_len = decode_var_int_from_stream(self.sock)
        puback_data = bytearray()
        while len(puback_data) < rem_len:
            chunk = self.sock.recv(rem_len - len(puback_data))
            if not chunk:
                raise ConnectionResetError("Truncated PUBACK")
            puback_data.extend(chunk)

        if rem_len == 2:
            return 0  # Implicit Success

        reason_code = puback_data[2]
        return reason_code

    def receive_message(self, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
        """Wait for an incoming PUBLISH message. Automatically sends PUBACK for QoS 1."""
        if not self.sock:
            raise RuntimeError("Not connected")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            r, _, _ = select.select([self.sock], [], [], remaining)
            if not r:
                return None

            try:
                pkt_type_b = self.sock.recv(1)
            except (socket.timeout, BlockingIOError):
                return None

            if not pkt_type_b:
                return None

            pkt_type = pkt_type_b[0]
            cmd = pkt_type & 0xF0
            flags = pkt_type & 0x0F

            rem_len = decode_var_int_from_stream(self.sock)
            body = bytearray()
            while len(body) < rem_len:
                chunk = self.sock.recv(rem_len - len(body))
                if not chunk:
                    return None
                body.extend(chunk)

            if cmd == 0x30:  # PUBLISH
                dup = bool(flags & 0x08)
                qos = (flags >> 1) & 0x03
                retain = bool(flags & 0x01)

                topic, offset = decode_str(body, 0)
                packet_id = 0
                if qos > 0:
                    packet_id = struct.unpack_from("!H", body, offset)[0]
                    offset += 2

                # Parse properties length
                prop_len = body[offset]  # Simple single-byte varint for properties
                offset += 1 + prop_len

                payload = bytes(body[offset:])

                # If QoS 1, reply with PUBACK Reason Code 0 (Success)
                if qos == 1:
                    puback = b"\x40\x02" + struct.pack("!H", packet_id)
                    self.sock.sendall(puback)

                return {
                    "topic": topic,
                    "payload": payload,
                    "qos": qos,
                    "retain": retain,
                    "dup": dup,
                    "packet_id": packet_id,
                }
            elif cmd == 0xD0:  # PINGRESP
                continue
            else:
                # Other control packets
                continue

        return None

    def disconnect(self) -> None:
        """Send DISCONNECT and close socket."""
        if self.sock:
            try:
                # DISCONNECT (0xE0) with Reason Code 0x00 and Property Length 0
                self.sock.sendall(b"\xe0\x02\x00\x00")
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
