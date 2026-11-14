package security

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"errors"
	"fmt"
	"io"
)

// AESGCMKeyWrapper implements key wrapping using AES-256-GCM.
type AESGCMKeyWrapper struct {
	masterKey [32]byte
}

// NewAESGCMKeyWrapper constructs a new AESGCMKeyWrapper from a 256-bit master key.
func NewAESGCMKeyWrapper(masterKey [32]byte) *AESGCMKeyWrapper {
	return &AESGCMKeyWrapper{masterKey: masterKey}
}

// Wrap encrypts plaintext with AES-256-GCM using a unique 12-byte CSPRNG nonce.
// Envelope format: nonce (12 bytes) || ciphertext + tag (len(plaintext) + 16 bytes).
func (w *AESGCMKeyWrapper) Wrap(plaintext []byte) ([]byte, error) {
	block, err := aes.NewCipher(w.masterKey[:])
	if err != nil {
		return nil, fmt.Errorf("aes cipher error: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm error: %w", err)
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, fmt.Errorf("failed to generate random nonce: %w", err)
	}

	ciphertext := gcm.Seal(nil, nonce, plaintext, nil)
	wrapped := make([]byte, 0, len(nonce)+len(ciphertext))
	wrapped = append(wrapped, nonce...)
	wrapped = append(wrapped, ciphertext...)
	return wrapped, nil
}

// Unwrap decrypts the wrapped ciphertext and verifies the GCM authentication tag.
func (w *AESGCMKeyWrapper) Unwrap(wrapped []byte) ([]byte, error) {
	block, err := aes.NewCipher(w.masterKey[:])
	if err != nil {
		return nil, fmt.Errorf("aes cipher error: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm error: %w", err)
	}
	nonceSize := gcm.NonceSize()
	if len(wrapped) < nonceSize+16 {
		return nil, errors.New("wrapped key payload too short")
	}
	nonce := wrapped[:nonceSize]
	ciphertext := wrapped[nonceSize:]
	return gcm.Open(nil, nonce, ciphertext, nil)
}
