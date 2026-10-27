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
	SuperframeSeq uint32  `json:"superframe_seq"`
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
		{"leading non-JSON whitespace", []byte("\u00a0{}"), 4096, nil},
		{"trailing non-JSON whitespace", []byte("{}\u00a0"), 4096, nil},
		{"vertical tab", []byte("\v{}"), 4096, nil},
		{"form feed", []byte("{}\f"), 4096, nil},
		{"trailing object", []byte("{} {}"), 4096, nil},
		{"duplicate root", []byte(`{"gateway_id":"gw01","gateway_id":"gw02"}`), 4096, nil},
		{"duplicate nested", []byte(`{"data":{"battery_mv":1,"battery_mv":2}}`), 4096, nil},
		{"unknown root", []byte(`{"unexpected":1}`), 4096, nil},
		{"unknown nested", []byte(`{"data":{"battery_mv":1,"unexpected":2}}`), 4096, nil},
		{"case mismatch", []byte(`{"Gateway_ID":"gw01"}`), 4096, nil},
		{"invalid UTF-8", []byte("{\"gateway_id\":\"\xff\"}"), 4096, nil},
		{"unpaired surrogate", []byte(`{"gateway_id":"\ud800"}`), 4096, nil},
		{"integer overflow", []byte(`{"data":{"battery_mv":65536}}`), 4096, nil},
		{"uint32 overflow", []byte(`{"superframe_seq":4294967296}`), 4096, nil},
		{"negative unsigned", []byte(`{"data":{"battery_mv":-1}}`), 4096, nil},
		{"trailing garbage", []byte(`{}x`), 4096, nil},
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
	for _, payload := range []string{
		`{"gateway_id":"gw01"}`,
		`{"gateway_id":"gw01","observed_at":null}`,
	} {
		var got testEnvelope
		if err := DecodeObject([]byte(payload), 4096, &got); err != nil {
			t.Fatalf("decode unexpectedly rejected syntactically valid partial DTO: %v", err)
		}
		if got.SchemaVersion != "" || got.ObservedAt != nil {
			t.Fatalf("unexpected schema or nullable field: %+v", got)
		}
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

func TestDecodeObjectCommitsOnlySuccessfulDecode(t *testing.T) {
	for _, payload := range []string{
		`{"gateway_id":"changed","unexpected":1}`,
		`{"gateway_id":"changed","data":{"battery_mv":65536}}`,
		`{"gateway_id":"changed"} {}`,
		`{"gateway_id":"changed","gateway_id":"duplicate"}`,
	} {
		dst := testEnvelope{GatewayID: "trusted", EventSeq: "123"}
		before := dst
		if err := DecodeObject([]byte(payload), 4096, &dst); err == nil {
			t.Fatal("invalid input accepted")
		}
		if dst != before {
			t.Fatalf("failed decode changed destination: %+v", dst)
		}
	}
	dst := testEnvelope{GatewayID: "stale", EventSeq: "123"}
	if err := DecodeObject([]byte(`{"gateway_id":"fresh"}`), 4096, &dst); err != nil {
		t.Fatal(err)
	}
	if dst.GatewayID != "fresh" || dst.EventSeq != "" {
		t.Fatalf("successful decode retained stale fields: %+v", dst)
	}
}

func TestDecodeObjectRejectsNilDestination(t *testing.T) {
	var dst *testEnvelope
	if err := DecodeObject([]byte(`{}`), 2, dst); err == nil {
		t.Fatal("nil destination accepted")
	}
}

func TestDecodeObjectAcceptsExactByteLimit(t *testing.T) {
	payload := []byte(" \r\n\t" + validEnvelope + "\t\r\n ")
	var dst testEnvelope
	if err := DecodeObject(payload, len(payload), &dst); err != nil {
		t.Fatal(err)
	}
	if err := DecodeObject(payload, len(payload)-1, &dst); !errors.Is(err, ErrTooLarge) {
		t.Fatalf("expected size limit error, got %v", err)
	}
}
