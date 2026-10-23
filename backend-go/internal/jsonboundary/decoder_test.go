package jsonboundary

import (
	"encoding/json"
	"errors"
	"testing"
)

type testEnvelope struct {
	SchemaVersion string  `json:"schema_version"`
	GatewayID     string  `json:"gateway_id"`
	EventSeq      string  `json:"event_seq"`
	ObservedAt    *string `json:"observed_at"`
	Data          struct {
		BatteryMV uint16 `json:"battery_mv"`
	} `json:"data"`
}

const validEnvelope = `{"schema_version":"1.0-draft","gateway_id":"gw01","event_seq":"18446744073709551615","observed_at":null,"data":{"battery_mv":3600}}`

func TestDecodeObjectAcceptsTypedEnvelope(t *testing.T) {
	var got testEnvelope
	if err := DecodeObject([]byte(" \n"+validEnvelope+"\t"), 4096, &got); err != nil {
		t.Fatalf("DecodeObject(valid): %v", err)
	}
	if got.SchemaVersion != "1.0-draft" || got.GatewayID != "gw01" ||
		got.EventSeq != "18446744073709551615" || got.ObservedAt != nil ||
		got.Data.BatteryMV != 3600 {
		t.Fatalf("wrong typed fields: %+v", got)
	}
}

func TestDecodeObjectRejectsUntrustedInput(t *testing.T) {
	tests := []struct {
		name    string
		payload []byte
		limit   int
		wantIs  error
	}{
		{"empty", []byte(""), 4096, ErrNotObject},
		{"null root", []byte("null"), 4096, ErrNotObject},
		{"array root", []byte("[]"), 4096, ErrNotObject},
		{"scalar root", []byte("42"), 4096, ErrNotObject},
		{"invalid syntax", []byte("{"), 4096, nil},
		{"trailing object", []byte("{} {}"), 4096, nil},
		{"duplicate root", []byte(`{"gateway_id":"gw01","gateway_id":"gw02"}`), 4096, nil},
		{"duplicate nested", []byte(`{"data":{"battery_mv":1,"battery_mv":2}}`), 4096, nil},
		{"unknown root", []byte(`{"unexpected":1}`), 4096, nil},
		{"unknown nested", []byte(`{"data":{"battery_mv":1,"unexpected":2}}`), 4096, nil},
		{"case mismatch", []byte(`{"Gateway_ID":"gw01"}`), 4096, nil},
		{"invalid UTF-8", []byte("{\"gateway_id\":\"\xff\"}"), 4096, nil},
		{"unpaired surrogate", []byte(`{"gateway_id":"\ud800"}`), 4096, nil},
		{"integer overflow", []byte(`{"data":{"battery_mv":65536}}`), 4096, nil},
		{"string identifier as number", []byte(`{"event_seq":18446744073709551615}`), 4096, nil},
		{"oversized", []byte(validEnvelope), 12, ErrTooLarge},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var dst testEnvelope
			err := DecodeObject(tt.payload, tt.limit, &dst)
			if err == nil {
				t.Fatal("DecodeObject() accepted invalid input")
			}
			if tt.wantIs != nil && !errors.Is(err, tt.wantIs) {
				t.Fatalf("errors.Is(%v, %v) = false", err, tt.wantIs)
			}
		})
	}
}

func TestDecodeObjectRejectsInvalidLimit(t *testing.T) {
	for _, limit := range []int{-1, 0} {
		var dst testEnvelope
		if err := DecodeObject([]byte(validEnvelope), limit, &dst); err == nil {
			t.Fatalf("limit %d accepted", limit)
		}
	}
}

func TestDecodeObjectDoesNotClaimSchemaValidation(t *testing.T) {
	// A decoder cannot enforce JSON Schema 'required' or 'const' constraints.
	// The caller must reject this message before DB writes or MQTT ACK.
	var got testEnvelope
	if err := DecodeObject([]byte(`{"gateway_id":"gw01"}`), 4096, &got); err != nil {
		t.Fatalf("decode unexpectedly rejected syntactically valid partial DTO: %v", err)
	}
	if got.SchemaVersion != "" {
		t.Fatalf("unexpected schema version: %q", got.SchemaVersion)
	}
}

func TestExistingV1JSONEncodingIsUnchanged(t *testing.T) {
	// The inbound decoder does not change external JSON serialization.
	out, err := json.Marshal(struct {
		Items []string `json:"items"`
	}{})
	if err != nil {
		t.Fatalf("Marshal: %v", err)
	}
	if string(out) != `{"items":null}` {
		t.Fatalf("unexpected legacy encoding: %s", out)
	}
}
