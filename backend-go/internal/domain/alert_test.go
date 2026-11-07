package domain_test

import (
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

func TestAlertFilter_Validate(t *testing.T) {
	nodeIDValid := uint8(10)
	nodeIDZero := uint8(0)
	nodeIDMax := uint8(254)
	nodeIDOver := uint8(255)

	tests := []struct {
		name    string
		filter  domain.AlertFilter
		wantErr bool
	}{
		{
			name: "valid empty filter",
			filter: domain.AlertFilter{
				Limit: 50,
			},
			wantErr: false,
		},
		{
			name: "valid populated filter",
			filter: domain.AlertFilter{
				Cursor:    "123",
				Limit:     100,
				Severity:  "P0_EMERGENCY",
				NodeID:    &nodeIDValid,
				GatewayID: "gw-01",
				AckStatus: "UNACKNOWLEDGED",
			},
			wantErr: false,
		},
		{
			name: "invalid negative limit",
			filter: domain.AlertFilter{
				Limit: -1,
			},
			wantErr: true,
		},
		{
			name: "invalid excessive limit",
			filter: domain.AlertFilter{
				Limit: 101,
			},
			wantErr: true,
		},
		{
			name: "invalid severity enum",
			filter: domain.AlertFilter{
				Severity: "CRITICAL",
			},
			wantErr: true,
		},
		{
			name: "invalid node_id zero",
			filter: domain.AlertFilter{
				NodeID: &nodeIDZero,
			},
			wantErr: true,
		},
		{
			name: "valid node_id max 254",
			filter: domain.AlertFilter{
				NodeID: &nodeIDMax,
			},
			wantErr: false,
		},
		{
			name: "invalid node_id 255",
			filter: domain.AlertFilter{
				NodeID: &nodeIDOver,
			},
			wantErr: true,
		},
		{
			name: "invalid ack_status enum",
			filter: domain.AlertFilter{
				AckStatus: "PENDING",
			},
			wantErr: true,
		},
		{
			name: "valid ack_status acknowledged",
			filter: domain.AlertFilter{
				AckStatus: "ACKNOWLEDGED",
			},
			wantErr: false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := tc.filter.Validate()
			if (err != nil) != tc.wantErr {
				t.Fatalf("Validate() error = %v, wantErr %v", err, tc.wantErr)
			}
		})
	}
}

func TestEventToAlertView(t *testing.T) {
	now := time.Now().UTC()
	obsAt := now.Add(-5 * time.Second)
	ackAt := now.Add(-1 * time.Second)
	ackBy := "operator-bob"

	event := &domain.Event{
		ID:        42,
		GatewayID: "gw-alpha",
		NodeID:    7,
		Data: domain.EventData{
			EventRef:   1001,
			EventCode:  1,
			EventValue: 1,
		},
		Severity:       domain.SeverityP1High,
		ObservedAt:     &obsAt,
		IngestedAt:     now,
		AckStatus:      domain.AckStatusAcknowledged,
		AcknowledgedAt: &ackAt,
		AcknowledgedBy: &ackBy,
		Trigger: &domain.EventTrigger{
			Channel:      2,
			ObservedRaw:  450,
			ThresholdRaw: 400,
		},
	}

	view := domain.EventToAlertView(event)

	if view.AlertID != "42" {
		t.Errorf("expected AlertID '42', got '%s'", view.AlertID)
	}
	if view.NodeID != 7 {
		t.Errorf("expected NodeID 7, got %d", view.NodeID)
	}
	if view.GatewayID != "gw-alpha" {
		t.Errorf("expected GatewayID 'gw-alpha', got '%s'", view.GatewayID)
	}
	if view.EventRef != 1001 {
		t.Errorf("expected EventRef 1001, got %d", view.EventRef)
	}
	if view.EventCode != 1 {
		t.Errorf("expected EventCode 1, got %d", view.EventCode)
	}
	if view.EventValue != 1 {
		t.Errorf("expected EventValue 1, got %d", view.EventValue)
	}
	if view.Severity != domain.SeverityP1High {
		t.Errorf("expected Severity P1_HIGH, got %s", view.Severity)
	}
	if view.TriggeredAt == nil || *view.TriggeredAt != obsAt.Format(time.RFC3339) {
		t.Errorf("unexpected TriggeredAt: %v", view.TriggeredAt)
	}
	if view.ReceivedAt != now.Format(time.RFC3339) {
		t.Errorf("unexpected ReceivedAt: %s", view.ReceivedAt)
	}
	if view.AckStatus != domain.AckStatusAcknowledged {
		t.Errorf("expected AckStatus ACKNOWLEDGED, got %s", view.AckStatus)
	}
	if view.AckedAt == nil || *view.AckedAt != ackAt.Format(time.RFC3339) {
		t.Errorf("unexpected AckedAt: %v", view.AckedAt)
	}
	if view.Trigger == nil || view.Trigger.Channel != 2 || view.Trigger.ObservedRaw != 450 || view.Trigger.ThresholdRaw != 400 {
		t.Errorf("unexpected Trigger: %+v", view.Trigger)
	}
}
