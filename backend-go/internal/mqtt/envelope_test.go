package mqtt_test

import (
	"encoding/hex"
	"strings"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
)

func validEnvelope() *mqtt.JoinHelloEnvelope {
	obsAt := "2026-11-07T12:00:00.000Z"
	rawHex := strings.Repeat("ab", 68)
	return &mqtt.JoinHelloEnvelope{
		SchemaVersion:      mqtt.SchemaVersionJoinHello,
		EventID:            "gw-alpha:12345678-1234-1234-1234-123456789abc:100",
		GatewayID:          "gw-alpha",
		GatewayEpoch:       "12345678-1234-1234-1234-123456789abc",
		EventSeq:           "100",
		ObservedAt:         &obsAt,
		ObservedTimeSource: mqtt.TimeSourceGatewayUTC,
		RadioRxMonotonicUS: "5000000",
		Buffered:           false,
		TargetGWID:         1,
		RawFrameHex:        rawHex,
		RSSI:               -85,
		SNR:                7.5,
	}
}

func TestJoinHelloEnvelope_Validate_Success(t *testing.T) {
	t.Parallel()

	env := validEnvelope()
	if err := env.Validate(); err != nil {
		t.Fatalf("expected valid envelope, got: %v", err)
	}

	// Unknown time source must have null observed_at
	env.ObservedTimeSource = mqtt.TimeSourceUnknown
	env.ObservedAt = nil
	if err := env.Validate(); err != nil {
		t.Fatalf("expected valid envelope with unknown time source, got: %v", err)
	}
}

func TestJoinHelloEnvelope_Validate_SchemaVersion(t *testing.T) {
	t.Parallel()

	env := validEnvelope()
	env.SchemaVersion = "2.0"
	if err := env.Validate(); err == nil {
		t.Fatal("expected error for invalid schema_version, got nil")
	}
}

func TestJoinHelloEnvelope_Validate_GatewayID(t *testing.T) {
	t.Parallel()

	for _, invalid := range []string{"", "gw/invalid", "gw with spaces", strings.Repeat("x", 33)} {
		env := validEnvelope()
		env.GatewayID = invalid
		if err := env.Validate(); err == nil {
			t.Fatalf("expected error for gateway_id %q, got nil", invalid)
		}
	}
}

func TestJoinHelloEnvelope_Validate_GatewayEpoch(t *testing.T) {
	t.Parallel()

	for _, invalid := range []string{"", "not-a-uuid", "12345678-1234-1234-1234"} {
		env := validEnvelope()
		env.GatewayEpoch = invalid
		if err := env.Validate(); err == nil {
			t.Fatalf("expected error for gateway_epoch %q, got nil", invalid)
		}
	}
}

func TestJoinHelloEnvelope_Validate_EventSeq(t *testing.T) {
	t.Parallel()

	for _, invalid := range []string{"", "-1", "01", "abc", "18446744073709551616"} {
		env := validEnvelope()
		env.EventSeq = invalid
		if err := env.Validate(); err == nil {
			t.Fatalf("expected error for event_seq %q, got nil", invalid)
		}
	}
}

func TestJoinHelloEnvelope_Validate_EventIDMismatch(t *testing.T) {
	t.Parallel()

	env := validEnvelope()
	env.EventID = "wrong:event:id"
	if err := env.Validate(); err == nil {
		t.Fatal("expected error for mismatched event_id, got nil")
	}
}

func TestJoinHelloEnvelope_Validate_ObservedAt(t *testing.T) {
	t.Parallel()

	// Missing when required
	env := validEnvelope()
	env.ObservedTimeSource = mqtt.TimeSourceGatewayUTC
	env.ObservedAt = nil
	if err := env.Validate(); err == nil {
		t.Fatal("expected error for nil observed_at with gateway_utc, got nil")
	}

	// Present when unknown
	badStr := "2026-11-07T12:00:00Z"
	env = validEnvelope()
	env.ObservedTimeSource = mqtt.TimeSourceUnknown
	env.ObservedAt = &badStr
	if err := env.Validate(); err == nil {
		t.Fatal("expected error for non-nil observed_at with unknown time source, got nil")
	}

	// Missing Z suffix
	noZ := "2026-11-07T12:00:00+07:00"
	env = validEnvelope()
	env.ObservedAt = &noZ
	if err := env.Validate(); err == nil {
		t.Fatal("expected error for observed_at without Z, got nil")
	}
}

func TestJoinHelloEnvelope_Validate_TargetGWID(t *testing.T) {
	t.Parallel()

	for _, invalid := range []int{0, 255, -1, 300} {
		env := validEnvelope()
		env.TargetGWID = invalid
		if err := env.Validate(); err == nil {
			t.Fatalf("expected error for target_gw_id %d, got nil", invalid)
		}
	}
}

func TestJoinHelloEnvelope_Validate_RawFrameHex(t *testing.T) {
	t.Parallel()

	for _, invalid := range []string{"", "short", strings.Repeat("z", 136), strings.Repeat("a", 135), strings.Repeat("a", 137)} {
		env := validEnvelope()
		env.RawFrameHex = invalid
		if err := env.Validate(); err == nil {
			t.Fatalf("expected error for raw_frame_hex %q, got nil", invalid)
		}
	}
}

func TestJoinHelloEnvelope_Validate_RSSI_SNR(t *testing.T) {
	t.Parallel()

	env := validEnvelope()
	env.RSSI = -141
	if err := env.Validate(); err == nil {
		t.Fatal("expected error for rssi -141, got nil")
	}
	env.RSSI = 1
	if err := env.Validate(); err == nil {
		t.Fatal("expected error for rssi 1, got nil")
	}

	env = validEnvelope()
	env.SNR = -30.1
	if err := env.Validate(); err == nil {
		t.Fatal("expected error for snr -30.1, got nil")
	}
	env.SNR = 30.1
	if err := env.Validate(); err == nil {
		t.Fatal("expected error for snr 30.1, got nil")
	}
}

func TestJoinHelloEnvelope_DecodeRawFrameHex(t *testing.T) {
	t.Parallel()

	env := validEnvelope()
	raw, err := env.DecodeRawFrameHex()
	if err != nil {
		t.Fatalf("expected successful decode, got: %v", err)
	}
	if len(raw) != 68 {
		t.Fatalf("expected 68 bytes, got: %d", len(raw))
	}
	expected, _ := hex.DecodeString(env.RawFrameHex)
	if string(raw) != string(expected) {
		t.Fatal("decoded bytes mismatch")
	}
}
