package mqtt

import (
	"context"
	"errors"
	"fmt"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security"
)

var (
	// ErrInvalidWrappedKey indicates the wrapped key format or length is invalid.
	ErrInvalidWrappedKey = errors.New("invalid wrapped key length or format")
)

// KeyUnwrapper abstracts pre-shared key unwrapping (e.g. from KMS or database envelope).
type KeyUnwrapper interface {
	UnwrapKJoin(ctx context.Context, networkID uint32, deviceMAC [6]byte, generation uint16, wrappedKey []byte) ([security.KeySize]byte, error)
}

// PlainKeyUnwrapper unwraps pre-shared keys stored as raw 32 bytes (for MVP/test usage).
type PlainKeyUnwrapper struct{}

// NewPlainKeyUnwrapper creates a new PlainKeyUnwrapper.
func NewPlainKeyUnwrapper() *PlainKeyUnwrapper {
	return &PlainKeyUnwrapper{}
}

// UnwrapKJoin extracts the 32-byte K_JOIN from the wrapped byte slice.
func (u *PlainKeyUnwrapper) UnwrapKJoin(ctx context.Context, networkID uint32, deviceMAC [6]byte, generation uint16, wrappedKey []byte) ([security.KeySize]byte, error) {
	if len(wrappedKey) != security.KeySize {
		return [security.KeySize]byte{}, fmt.Errorf("%w: expected %d bytes, got %d", ErrInvalidWrappedKey, security.KeySize, len(wrappedKey))
	}

	var kJoin [security.KeySize]byte
	copy(kJoin[:], wrappedKey)
	return kJoin, nil
}
