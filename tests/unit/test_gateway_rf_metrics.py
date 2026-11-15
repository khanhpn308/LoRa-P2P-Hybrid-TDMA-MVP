"""
Unit and contract consistency tests for Gateway LoRa RF metrics math and schema.

Authority: Issue #392, Semtech SX1276 Datasheet §5.5.5, ADR-0004, contracts/mqtt/topics.md.
"""

import json
from pathlib import Path
import unittest
import jsonschema


def calculate_packet_rssi_c(reg_rssi: int, raw_snr: int, hf_offset: int = -157) -> int:
    """Exact C integer logic as implemented in sx1276_owner.c:

    if (snr_quarter >= 0) {
        rssi = hf_offset + reg_rssi;
    } else {
        int16_t snr_round = (int16_t)((snr_quarter - 2) / 4);
        rssi = hf_offset + reg_rssi + snr_round;
    }
    """
    if raw_snr >= 0:
        return hf_offset + reg_rssi
    else:
        # In C, integer division of negative numbers truncates toward zero:
        # e.g. (-31 - 2) / 4 = -33 / 4 = -8
        return hf_offset + reg_rssi + int((raw_snr - 2) / 4)


def calculate_snr_db(raw_snr: int) -> float:
    return float(raw_snr) / 4.0


class TestGatewayRfMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.alert_schema_path = cls.repo_root / "contracts" / "mqtt" / "schemas" / "alert.schema.json"
        cls.rf_metrics_schema_path = cls.repo_root / "contracts" / "mqtt" / "schemas" / "rf-metrics.schema.json"

        with open(cls.alert_schema_path, "r", encoding="utf-8") as f:
            cls.alert_schema = json.load(f)

        with open(cls.rf_metrics_schema_path, "r", encoding="utf-8") as f:
            cls.rf_metrics_schema = json.load(f)

    def test_snr_raw_conversion(self):
        """Verify raw RegPktSnrValue conversion to float dB with 0.25 dB resolution."""
        # -31 -> -7.75 dB
        self.assertAlmostEqual(calculate_snr_db(-31), -7.75, places=2)
        # 0 -> 0.0 dB
        self.assertAlmostEqual(calculate_snr_db(0), 0.0, places=2)
        # 20 -> 5.0 dB
        self.assertAlmostEqual(calculate_snr_db(20), 5.0, places=2)
        # -4 -> -1.0 dB
        self.assertAlmostEqual(calculate_snr_db(-4), -1.0, places=2)
        # -1 -> -0.25 dB
        self.assertAlmostEqual(calculate_snr_db(-1), -0.25, places=2)

    def test_negative_snr_nearest_integer_rounding(self):
        """Verify symmetric nearest-integer rounding for negative SNR RSSI correction (Issue #392).

        Formula: (snr_quarter - 2) / 4
        """
        reg_rssi = 100
        hf_offset = -157

        # snr = 0 (>= 0): rssi = -157 + 100 = -57 dBm
        self.assertEqual(calculate_packet_rssi_c(reg_rssi, 0, hf_offset), -57)

        # snr = -31 (-7.75 dB): round(-7.75) = -8 -> rssi = -157 + 100 - 8 = -65 dBm
        # (-31 - 2) / 4 = -33 / 4 = -8
        self.assertEqual(calculate_packet_rssi_c(reg_rssi, -31, hf_offset), -65)

        # snr = -1 (-0.25 dB): (-1 - 2) / 4 = -3 / 4 = 0 (towards zero in C)
        self.assertEqual(calculate_packet_rssi_c(reg_rssi, -1, hf_offset), -57)

        # snr = -2 (-0.50 dB): (-2 - 2) / 4 = -4 / 4 = -1
        self.assertEqual(calculate_packet_rssi_c(reg_rssi, -2, hf_offset), -58)

        # snr = -3 (-0.75 dB): (-3 - 2) / 4 = -5 / 4 = -1
        self.assertEqual(calculate_packet_rssi_c(reg_rssi, -3, hf_offset), -58)

        # snr = -4 (-1.00 dB): (-4 - 2) / 4 = -6 / 4 = -1
        self.assertEqual(calculate_packet_rssi_c(reg_rssi, -4, hf_offset), -58)

        # snr = -5 (-1.25 dB): (-5 - 2) / 4 = -7 / 4 = -1
        self.assertEqual(calculate_packet_rssi_c(reg_rssi, -5, hf_offset), -58)

        # snr = -6 (-1.50 dB): (-6 - 2) / 4 = -8 / 4 = -2
        self.assertEqual(calculate_packet_rssi_c(reg_rssi, -6, hf_offset), -59)

    def test_alert_schema_with_and_without_rf(self):
        """Verify alert schema backward compatibility: valid without 'rf', and valid with 'rf'."""
        base_alert = {
            "schema_version": "1.0-draft",
            "event_id": "gw01:550e8400-e29b-41d4-a716-446655440000:42",
            "gateway_id": "gw01",
            "gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
            "event_seq": "42",
            "observed_at": "2026-10-20T08:00:00Z",
            "observed_time_source": "gateway_utc",
            "radio_rx_monotonic_us": "123456789",
            "buffered": False,
            "node_id": 1,
            "superframe_seq": 100,
            "seq_num": 51,
            "schedule_version": 5,
            "data": {
                "event_ref": 1,
                "event_code": 1,
                "event_value": 1
            },
            "severity": "P0_EMERGENCY",
            "radio_ack_sent": True
        }
        # Without rf -> Valid
        jsonschema.validate(base_alert, self.alert_schema)

        # With rf -> Valid
        alert_with_rf = dict(base_alert)
        alert_with_rf["rf"] = {
            "channel_idx": 3,
            "gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
            "sample_seq": "1007",
            "rx_monotonic_us": "123456789",
            "rssi_dbm": -82,
            "snr_db": -7.75
        }
        jsonschema.validate(alert_with_rf, self.alert_schema)

        # Invalid rf channel_idx (11 > max 10)
        invalid_alert = dict(base_alert)
        invalid_alert["rf"] = dict(alert_with_rf["rf"])
        invalid_alert["rf"]["channel_idx"] = 11
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid_alert, self.alert_schema)

        # Invalid snr_db (out of [-50.0, 50.0])
        invalid_alert_snr = dict(base_alert)
        invalid_alert_snr["rf"] = dict(alert_with_rf["rf"])
        invalid_alert_snr["rf"]["snr_db"] = 55.0
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid_alert_snr, self.alert_schema)

    def test_rf_metrics_schema_validation(self):
        """Verify rf-metrics.schema.json validates NODE_UPLINK, CHANNEL, and batch structures."""
        # 1. Single NODE_UPLINK
        node_payload = {
            "schema_version": "1.0-draft",
            "gateway_id": "gw01",
            "gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
            "sample_seq": "1001",
            "sample_monotonic_us": "1234567890",
            "age_ms": 15,
            "kind": "NODE_UPLINK",
            "channel_idx": 4,
            "node_id": 12,
            "rssi_dbm": -88,
            "snr_db": -7.75,
            "source": "UP_EVENT",
            "validation": "VERIFIED"
        }
        jsonschema.validate(node_payload, self.rf_metrics_schema)

        # 2. Single CHANNEL
        channel_payload = {
            "schema_version": "1.0-draft",
            "gateway_id": "gw01",
            "gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
            "sample_seq": "1002",
            "sample_monotonic_us": "1234568000",
            "age_ms": 5,
            "kind": "CHANNEL",
            "channel_idx": 0,
            "channel_rssi_dbm": -105,
            "sample_context": "RX_IDLE"
        }
        jsonschema.validate(channel_payload, self.rf_metrics_schema)

        # 3. Batch
        batch_payload = {
            "schema_version": "1.0-draft",
            "gateway_id": "gw01",
            "gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
            "samples": [
                {
                    "sample_seq": "1003",
                    "sample_monotonic_us": "1234568500",
                    "age_ms": 10,
                    "kind": "NODE_UPLINK",
                    "channel_idx": 0,
                    "node_id": 2,
                    "rssi_dbm": -65,
                    "snr_db": -7.75,
                    "source": "UP_EVENT",
                    "validation": "VERIFIED"
                },
                {
                    "sample_seq": "1004",
                    "sample_monotonic_us": "1234568550",
                    "age_ms": 8,
                    "kind": "CHANNEL",
                    "channel_idx": 0,
                    "channel_rssi_dbm": -104,
                    "sample_context": "RX_IDLE"
                }
            ]
        }
        jsonschema.validate(batch_payload, self.rf_metrics_schema)

    def test_boot_epoch_uuid_validation_and_reboot_transition(self):
        """Verify strict UUID validation matching C implementation and schema validation across reboot."""
        def is_valid_uuid_c(u):
            if u is None or len(u) != 36:
                return False
            for i, c in enumerate(u):
                if i in (8, 13, 18, 23):
                    if c != "-":
                        return False
                else:
                    if not ((c >= "0" and c <= "9") or (c >= "a" and c <= "f") or (c >= "A" and c <= "F")):
                        return False
            return True

        # Valid UUIDs
        self.assertTrue(is_valid_uuid_c("550e8400-e29b-41d4-a716-446655440000"))
        self.assertTrue(is_valid_uuid_c("01234567-89ab-cdef-0123-456789abcdef"))
        self.assertTrue(is_valid_uuid_c("A1B2C3D4-E5F6-4A7B-8C9D-0E1F2A3B4C5D"))

        # Invalid UUIDs
        self.assertFalse(is_valid_uuid_c(None))
        self.assertFalse(is_valid_uuid_c(""))
        self.assertFalse(is_valid_uuid_c("not-a-uuid"))
        self.assertFalse(is_valid_uuid_c("550e8400-e29b-41d4-a716-44665544000")) # 35 chars
        self.assertFalse(is_valid_uuid_c("550e8400-e29b-41d4-a716-4466554400000")) # 37 chars
        self.assertFalse(is_valid_uuid_c("550e8400_e29b_41d4_a716_446655440000")) # underscores
        self.assertFalse(is_valid_uuid_c("550e8400-e29b-41d4-a716-44665544000g")) # non-hex 'g'

        # Verify alert payload across reboot (new epoch, lower seq) validates against alert schema
        epoch1 = "550e8400-e29b-41d4-a716-446655440000"
        epoch2 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"

        pre_reboot_alert = {
            "schema_version": "1.0-draft",
            "event_id": f"gw-a:{epoch1}:1050",
            "gateway_id": "gw-a",
            "gateway_epoch": epoch1,
            "event_seq": "1050",
            "observed_at": None,
            "observed_time_source": "unknown",
            "radio_rx_monotonic_us": "9876543210",
            "buffered": False,
            "node_id": 3,
            "superframe_seq": 100,
            "seq_num": 51,
            "schedule_version": 1,
            "data": {"event_ref": 62, "event_code": 1, "event_value": 25},
            "severity": "P3_NORMAL",
            "radio_ack_sent": True,
            "rf": {
                "channel_idx": 2,
                "gateway_epoch": epoch1,
                "sample_seq": "1050",
                "rx_monotonic_us": "9876543210",
                "rssi_dbm": -85,
                "snr_db": 6.5
            }
        }
        jsonschema.validate(pre_reboot_alert, self.alert_schema)

        # Post-reboot: new epoch, reset sequence = 1
        post_reboot_alert = {
            "schema_version": "1.0-draft",
            "event_id": f"gw-a:{epoch2}:1",
            "gateway_id": "gw-a",
            "gateway_epoch": epoch2,
            "event_seq": "1",
            "observed_at": None,
            "observed_time_source": "unknown",
            "radio_rx_monotonic_us": "1000000",
            "buffered": False,
            "node_id": 3,
            "superframe_seq": 1,
            "seq_num": 1,
            "schedule_version": 1,
            "data": {"event_ref": 63, "event_code": 1, "event_value": 26},
            "severity": "P3_NORMAL",
            "radio_ack_sent": True,
            "rf": {
                "channel_idx": 2,
                "gateway_epoch": epoch2,
                "sample_seq": "1",
                "rx_monotonic_us": "1000000",
                "rssi_dbm": -72,
                "snr_db": 9.25
            }
        }
        jsonschema.validate(post_reboot_alert, self.alert_schema)

        # Post-reboot alert when optional RF formatting fails (valid alert without rf block)
        post_reboot_no_rf = {
            "schema_version": "1.0-draft",
            "event_id": f"gw-a:{epoch2}:64",
            "gateway_id": "gw-a",
            "gateway_epoch": epoch2,
            "event_seq": "64",
            "observed_at": None,
            "observed_time_source": "unknown",
            "radio_rx_monotonic_us": "2000000",
            "buffered": False,
            "node_id": 3,
            "superframe_seq": 1,
            "seq_num": 2,
            "schedule_version": 1,
            "data": {"event_ref": 64, "event_code": 1, "event_value": 27},
            "severity": "P3_NORMAL",
            "radio_ack_sent": True
        }
        jsonschema.validate(post_reboot_no_rf, self.alert_schema)


if __name__ == "__main__":
    unittest.main()
