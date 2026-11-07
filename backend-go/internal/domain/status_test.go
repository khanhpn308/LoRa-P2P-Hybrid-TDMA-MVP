package domain

import (
	"testing"
	"time"
)

func TestGatewayStatusRecord_Validate(t *testing.T) {
	ch := "CH04"
	invalidCh := "CH99"

	tests := []struct {
		name    string
		record  GatewayStatusRecord
		wantErr bool
	}{
		{
			name: "valid record",
			record: GatewayStatusRecord{
				GatewayID:             "gw-alpha-01",
				GatewayEpoch:          "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				Mode:                  GatewayModeActive,
				ActiveScheduleVersion: 42,
				ChannelID:             &ch,
				RFDutyPermille:        100,
				NodeCount:             5,
				FreeHeapBytes:         150000,
				OfflineQueueCount:     0,
				PendingEventCount:     3,
				DroppedEventCount:     0,
				LastSeenAt:            time.Now().UTC(),
				UpdatedAt:             time.Now().UTC(),
			},
			wantErr: false,
		},
		{
			name: "invalid gateway_id",
			record: GatewayStatusRecord{
				GatewayID:    "gw invalid!",
				GatewayEpoch: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				Mode:         GatewayModeActive,
			},
			wantErr: true,
		},
		{
			name: "invalid gateway_epoch",
			record: GatewayStatusRecord{
				GatewayID:    "gw-01",
				GatewayEpoch: "not-a-uuid",
				Mode:         GatewayModeActive,
			},
			wantErr: true,
		},
		{
			name: "invalid mode",
			record: GatewayStatusRecord{
				GatewayID:    "gw-01",
				GatewayEpoch: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				Mode:         "UNKNOWN_MODE",
			},
			wantErr: true,
		},
		{
			name: "negative rf duty",
			record: GatewayStatusRecord{
				GatewayID:      "gw-01",
				GatewayEpoch:   "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				Mode:           GatewayModeActive,
				RFDutyPermille: -1,
			},
			wantErr: true,
		},
		{
			name: "rf duty > 1000",
			record: GatewayStatusRecord{
				GatewayID:      "gw-01",
				GatewayEpoch:   "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				Mode:           GatewayModeActive,
				RFDutyPermille: 1001,
			},
			wantErr: true,
		},
		{
			name: "node count > 254",
			record: GatewayStatusRecord{
				GatewayID:    "gw-01",
				GatewayEpoch: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				Mode:         GatewayModeActive,
				NodeCount:    255,
			},
			wantErr: true,
		},
		{
			name: "invalid channel id",
			record: GatewayStatusRecord{
				GatewayID:    "gw-01",
				GatewayEpoch: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				Mode:         GatewayModeActive,
				ChannelID:    &invalidCh,
			},
			wantErr: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := tc.record.Validate()
			if (err != nil) != tc.wantErr {
				t.Fatalf("expected wantErr=%v, got err=%v", tc.wantErr, err)
			}
		})
	}
}

func TestNodeFilter_Validate(t *testing.T) {
	tests := []struct {
		name    string
		filter  NodeFilter
		wantErr bool
	}{
		{
			name: "valid default filter",
			filter: NodeFilter{
				Limit: 50,
			},
			wantErr: false,
		},
		{
			name: "valid full filter",
			filter: NodeFilter{
				GatewayID: "gw-01",
				Status:    "ONLINE",
				Limit:     100,
			},
			wantErr: false,
		},
		{
			name: "invalid limit 0",
			filter: NodeFilter{
				Limit: 0,
			},
			wantErr: true,
		},
		{
			name: "invalid limit > 100",
			filter: NodeFilter{
				Limit: 101,
			},
			wantErr: true,
		},
		{
			name: "invalid gateway id",
			filter: NodeFilter{
				GatewayID: "gw invalid?",
				Limit:     10,
			},
			wantErr: true,
		},
		{
			name: "invalid status",
			filter: NodeFilter{
				Status: "INVALID_STATUS",
				Limit:  10,
			},
			wantErr: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := tc.filter.Validate()
			if (err != nil) != tc.wantErr {
				t.Fatalf("expected wantErr=%v, got err=%v", tc.wantErr, err)
			}
		})
	}
}
