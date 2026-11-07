package mqtt_test

import (
	"errors"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
)

func TestBuildJoinHelloTopic(t *testing.T) {
	t.Parallel()

	topic := mqtt.BuildJoinHelloTopic("gw-alpha")
	expected := "iot/v1/gw/gw-alpha/uplink/join-hello"
	if topic != expected {
		t.Fatalf("expected %q, got %q", expected, topic)
	}
}

func TestParseJoinHelloTopic_Success(t *testing.T) {
	t.Parallel()

	gwID, err := mqtt.ParseJoinHelloTopic("iot/v1/gw/gw-alpha-01/uplink/join-hello")
	if err != nil {
		t.Fatalf("expected successful parse, got: %v", err)
	}
	if gwID != "gw-alpha-01" {
		t.Fatalf("expected gw-alpha-01, got %q", gwID)
	}
}

func TestParseJoinHelloTopic_Malformed(t *testing.T) {
	t.Parallel()

	testCases := []string{
		"",
		"iot/v1/gw/uplink/join-hello", // slice bounds regression check
		"iot/v1/gw//uplink/join-hello",
		"iot/v1/gw/gw-alpha/downlink/schedule",
		"other/v1/gw/gw-alpha/uplink/join-hello",
		"iot/v1/gw/gw/sub/uplink/join-hello",
		"iot/v1/gw/gw!invalid/uplink/join-hello",
	}

	for _, tc := range testCases {
		_, err := mqtt.ParseJoinHelloTopic(tc)
		if err == nil {
			t.Fatalf("expected error for malformed topic %q, got nil", tc)
		}
		if !errors.Is(err, mqtt.ErrMalformedTopic) {
			t.Fatalf("expected ErrMalformedTopic for %q, got: %v", tc, err)
		}
	}
}
