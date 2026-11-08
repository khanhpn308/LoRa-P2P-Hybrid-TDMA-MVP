package realtime

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func TestAlertTriggeredPayload_Validation(t *testing.T) {
	validTime := "2026-11-08T00:50:00Z"

	tests := []struct {
		name    string
		payload AlertTriggeredPayload
		wantErr bool
	}{
		{
			name: "valid alert payload",
			payload: AlertTriggeredPayload{
				GatewayID:   "gw-01",
				NodeID:      5,
				AlertID:     "1001",
				EventRef:    42,
				EventCode:   1,
				EventValue:  100,
				Severity:    "P0_EMERGENCY",
				TriggeredAt: &validTime,
			},
			wantErr: false,
		},
		{
			name: "invalid gateway id - special chars",
			payload: AlertTriggeredPayload{
				GatewayID: "gw@invalid!",
				NodeID:    5,
				AlertID:   "1001",
				Severity:  "P1_HIGH",
			},
			wantErr: true,
		},
		{
			name: "invalid node id - zero",
			payload: AlertTriggeredPayload{
				GatewayID: "gw-01",
				NodeID:    0,
				AlertID:   "1001",
				Severity:  "P2_MEDIUM",
			},
			wantErr: true,
		},
		{
			name: "invalid node id - out of bounds",
			payload: AlertTriggeredPayload{
				GatewayID: "gw-01",
				NodeID:    255,
				AlertID:   "1001",
				Severity:  "P2_MEDIUM",
			},
			wantErr: true,
		},
		{
			name: "invalid alert id - non numeric",
			payload: AlertTriggeredPayload{
				GatewayID: "gw-01",
				NodeID:    5,
				AlertID:   "abc",
				Severity:  "P3_NORMAL",
			},
			wantErr: true,
		},
		{
			name: "invalid severity enum",
			payload: AlertTriggeredPayload{
				GatewayID: "gw-01",
				NodeID:    5,
				AlertID:   "1001",
				Severity:  "CRITICAL",
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.payload.Validate()
			if (err != nil) != tt.wantErr {
				t.Fatalf("Validate() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestScheduleStateChangedPayload_Validation(t *testing.T) {
	tests := []struct {
		name    string
		payload ScheduleStateChangedPayload
		wantErr bool
	}{
		{
			name: "valid schedule state - ACTIVE",
			payload: ScheduleStateChangedPayload{
				GatewayID:  "gw-main",
				ScheduleID: "42",
				Version:    1,
				State:      "ACTIVE",
			},
			wantErr: false,
		},
		{
			name: "valid schedule state - STAGED",
			payload: ScheduleStateChangedPayload{
				GatewayID:  "gw-main",
				ScheduleID: "42",
				Version:    1,
				State:      "STAGED",
			},
			wantErr: false,
		},
		{
			name: "invalid state enum",
			payload: ScheduleStateChangedPayload{
				GatewayID:  "gw-main",
				ScheduleID: "42",
				Version:    1,
				State:      "RUNNING",
			},
			wantErr: true,
		},
		{
			name: "invalid schedule id format",
			payload: ScheduleStateChangedPayload{
				GatewayID:  "gw-main",
				ScheduleID: "sched-42",
				Version:    1,
				State:      "ACTIVE",
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.payload.Validate()
			if (err != nil) != tt.wantErr {
				t.Fatalf("Validate() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestGatewayStatusChangedPayload_Validation(t *testing.T) {
	nowStr := "2026-11-08T00:50:00Z"

	tests := []struct {
		name    string
		payload GatewayStatusChangedPayload
		wantErr bool
	}{
		{
			name: "valid gateway mode - ACTIVE",
			payload: GatewayStatusChangedPayload{
				GatewayID:  "gw-01",
				Mode:       "ACTIVE",
				LastSeenAt: &nowStr,
			},
			wantErr: false,
		},
		{
			name: "valid gateway mode - OFFLINE",
			payload: GatewayStatusChangedPayload{
				GatewayID:  "gw-01",
				Mode:       "OFFLINE",
				LastSeenAt: nil,
			},
			wantErr: false,
		},
		{
			name: "invalid mode enum",
			payload: GatewayStatusChangedPayload{
				GatewayID:  "gw-01",
				Mode:       "SLEEPING",
				LastSeenAt: nil,
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.payload.Validate()
			if (err != nil) != tt.wantErr {
				t.Fatalf("Validate() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestTelemetryUpdatePayload_Validation(t *testing.T) {
	tests := []struct {
		name    string
		payload TelemetryUpdatePayload
		wantErr bool
	}{
		{
			name: "valid telemetry payload",
			payload: TelemetryUpdatePayload{
				GatewayID: "gw-01",
				NodeID:    3,
				ReadingID: "12345",
				EventID:   "gw-01:12345678-1234-1234-1234-123456789abc:10",
				Data: TelemetryData{
					Ch1Raw:    100,
					Ch2Raw:    200,
					Ch3Raw:    300,
					BatteryMv: 3300,
				},
			},
			wantErr: false,
		},
		{
			name: "invalid reading id",
			payload: TelemetryUpdatePayload{
				GatewayID: "gw-01",
				NodeID:    3,
				ReadingID: "read-123",
				EventID:   "gw-01:12345678-1234-1234-1234-123456789abc:10",
			},
			wantErr: true,
		},
		{
			name: "invalid source event id format",
			payload: TelemetryUpdatePayload{
				GatewayID: "gw-01",
				NodeID:    3,
				ReadingID: "12345",
				EventID:   "invalid-event-id",
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.payload.Validate()
			if (err != nil) != tt.wantErr {
				t.Fatalf("Validate() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestEnvelopeConstruction_SchemaCompliance(t *testing.T) {
	payload := AlertTriggeredPayload{
		GatewayID:  "gw-alpha",
		NodeID:     2,
		AlertID:    "99",
		EventRef:   1,
		EventCode:  1,
		EventValue: 1,
		Severity:   "P0_EMERGENCY",
	}

	env, err := NewAlertTriggeredEvent(payload, nil)
	if err != nil {
		t.Fatalf("NewAlertTriggeredEvent failed: %v", err)
	}

	if env.SchemaVersion != "1.0-draft" {
		t.Errorf("expected schema_version 1.0-draft, got %s", env.SchemaVersion)
	}
	if env.Type != EventTypeAlertTriggered {
		t.Errorf("expected type ALERT_TRIGGERED, got %s", env.Type)
	}
	if !strings.HasSuffix(env.EmittedAt, "Z") {
		t.Errorf("expected emitted_at to end with 'Z', got %s", env.EmittedAt)
	}
	if len(env.EventID) != 36 {
		t.Errorf("expected 36-char UUID for event_id, got %s", env.EventID)
	}

	// Verify JSON marshaling produces valid JSON matching schema
	data, err := json.Marshal(env)
	if err != nil {
		t.Fatalf("json.Marshal failed: %v", err)
	}

	var parsed map[string]any
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("json.Unmarshal failed: %v", err)
	}

	if parsed["schema_version"] != "1.0-draft" {
		t.Errorf("json missing schema_version")
	}
	if parsed["event_id"] != env.EventID {
		t.Errorf("json event_id mismatch")
	}
}

func TestFormatUTCZ(t *testing.T) {
	fixedTime := time.Date(2026, 11, 8, 3, 15, 30, 0, time.UTC)
	formatted := FormatUTCZ(fixedTime)
	expected := "2026-11-08T03:15:30Z"
	if formatted != expected {
		t.Errorf("expected %s, got %s", expected, formatted)
	}
}
