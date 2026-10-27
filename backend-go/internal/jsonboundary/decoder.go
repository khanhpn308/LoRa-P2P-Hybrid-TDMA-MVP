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
// Use plain struct DTOs without custom unmarshal methods or untyped fields.
// Decoding starts from a zero value; errors leave dst unchanged.
// This function does not write to a database or acknowledge MQTT messages.
func DecodeObject[T any](payload []byte, maxBytes int, dst *T) error {
	if maxBytes <= 0 {
		return fmt.Errorf("JSON size limit must be positive: %d", maxBytes)
	}
	if len(payload) > maxBytes {
		return fmt.Errorf("%w: limit %d bytes", ErrTooLarge, maxBytes)
	}

	data := bytes.Trim(payload, " \t\r\n")
	if len(data) == 0 || data[0] != '{' {
		return ErrNotObject
	}

	if dst == nil {
		return errors.New("JSON destination must be non-nil")
	}

	var decoded T
	if err := json.Unmarshal(data, &decoded, json.RejectUnknownMembers(true)); err != nil {
		return fmt.Errorf("decode JSON object: %w", err)
	}
	*dst = decoded
	return nil
}
