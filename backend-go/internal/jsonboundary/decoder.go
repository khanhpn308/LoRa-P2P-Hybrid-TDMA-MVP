// Package jsonboundary decodes untrusted JSON objects before domain validation.
// It does not implement JSON Schema or perform persistence.
package jsonboundary

import (
	"bytes"
	"encoding/json/v2"
	"errors"
	"fmt"
)

// ErrTooLarge reports that a payload exceeds its caller-approved byte limit.
var ErrTooLarge = errors.New("JSON payload exceeds size limit")

// ErrNotObject reports that the root is not a JSON object.
var ErrNotObject = errors.New("JSON payload must be a non-null object")

// DecodeObject decodes one untrusted JSON object into a typed destination.
//
// Go 1.27 json/v2 rejects duplicate object members and invalid UTF-8 by default.
// RejectUnknownMembers also rejects fields absent from typed struct DTOs.
// Callers must validate required fields, schema version, numeric ranges,
// cross-field invariants, and the relevant JSON Schema before any side effect.
// This function does not write to a database or acknowledge MQTT messages.
func DecodeObject(payload []byte, maxBytes int, dst any) error {
	if maxBytes <= 0 {
		return fmt.Errorf("JSON size limit must be positive: %d", maxBytes)
	}
	if len(payload) > maxBytes {
		return fmt.Errorf("%w: limit %d bytes", ErrTooLarge, maxBytes)
	}

	data := bytes.TrimSpace(payload)
	if len(data) == 0 || data[0] != '{' {
		return ErrNotObject
	}

	if err := json.Unmarshal(data, dst, json.RejectUnknownMembers(true)); err != nil {
		return fmt.Errorf("decode JSON object: %w", err)
	}
	return nil
}
