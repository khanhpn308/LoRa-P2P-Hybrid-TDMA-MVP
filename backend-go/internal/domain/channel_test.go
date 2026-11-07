package domain_test

import (
	"fmt"
	"strings"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

func TestApprovedVN920Catalogue(t *testing.T) {
	if len(domain.ApprovedVN920Catalogue) != domain.ChannelCountVN920 {
		t.Fatalf("expected %d channels, got %d", domain.ChannelCountVN920, len(domain.ApprovedVN920Catalogue))
	}

	startFreq := int64(920250000)
	stepHz := int64(250000)

	for i := 0; i < domain.ChannelCountVN920; i++ {
		chID := fmt.Sprintf("CH%02d", i)
		expectedFreq := startFreq + int64(i)*stepHz

		freq, err := domain.GetApprovedFrequencyHz(chID)
		if err != nil {
			t.Errorf("channel %s missing in catalogue: %v", chID, err)
			continue
		}

		if freq != expectedFreq {
			t.Errorf("channel %s frequency mismatch: expected %d Hz, got %d Hz", chID, expectedFreq, freq)
		}
	}
}

func TestValidateChannelID(t *testing.T) {
	tests := []struct {
		name      string
		channelID string
		wantErr   bool
	}{
		{"valid CH00", "CH00", false},
		{"valid CH05", "CH05", false},
		{"valid CH10", "CH10", false},
		{"out of range CH11", "CH11", true},
		{"negative index CH-1", "CH-1", true},
		{"empty channel", "", true},
		{"lowercase ch00", "ch00", true},
		{"arbitrary text", "LORA_920", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := domain.ValidateChannelID(tt.channelID)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateChannelID(%q) error = %v, wantErr = %v", tt.channelID, err, tt.wantErr)
			}
		})
	}
}

func TestValidateChannelPlanVersion(t *testing.T) {
	tests := []struct {
		name    string
		version string
		wantErr bool
	}{
		{"valid VN920_V1", "VN920_V1", false},
		{"empty version", "", true},
		{"wrong version VN920_V2", "VN920_V2", true},
		{"unapproved EU868", "EU868", true},
		{"unapproved US915", "US915", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := domain.ValidateChannelPlanVersion(tt.version)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateChannelPlanVersion(%q) error = %v, wantErr = %v", tt.version, err, tt.wantErr)
			}
		})
	}
}

func TestValidateGatewayID(t *testing.T) {
	tests := []struct {
		name    string
		gwID    string
		wantErr bool
	}{
		{"valid gw01", "gw01", false},
		{"valid complex", "gw-station_01", false},
		{"empty", "", true},
		{"contains space", "gw 01", true},
		{"contains colon", "gw:01", true},
		{"contains slash", "gw/01", true},
		{"too long", strings.Repeat("a", 65), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := domain.ValidateGatewayID(tt.gwID)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateGatewayID(%q) error = %v, wantErr = %v", tt.gwID, err, tt.wantErr)
			}
		})
	}
}

func TestValidateRequestID(t *testing.T) {
	tests := []struct {
		name    string
		reqID   string
		wantErr bool
	}{
		{"valid uuid", "550e8400-e29b-41d4-a716-446655440000", false},
		{"valid simple", "req-12345", false},
		{"empty", "", true},
		{"contains space", "req 123", true},
		{"too long", strings.Repeat("x", 129), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := domain.ValidateRequestID(tt.reqID)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateRequestID(%q) error = %v, wantErr = %v", tt.reqID, err, tt.wantErr)
			}
		})
	}
}

func TestRegulatoryNotice(t *testing.T) {
	if domain.RegulatoryNotice == "" {
		t.Fatal("RegulatoryNotice must not be empty")
	}
	if !strings.Contains(domain.RegulatoryNotice, "ERP") {
		t.Error("RegulatoryNotice must document ERP boundary")
	}
	if !strings.Contains(domain.RegulatoryNotice, "duty cycle") {
		t.Error("RegulatoryNotice must document duty cycle boundary")
	}
}
