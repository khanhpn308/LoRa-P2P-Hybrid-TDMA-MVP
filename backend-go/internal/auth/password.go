package auth

import (
	"errors"
	"fmt"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth/bcrypt"
)

// DefaultBcryptCost specifies the minimum bcrypt hashing cost factor (SE-003: cost >= 12).
const DefaultBcryptCost = 12

// HashPassword securely hashes a plaintext password using bcrypt with cost >= 12.
func HashPassword(password string) (string, error) {
	if len(password) < 8 {
		return "", errors.New("password must be at least 8 characters")
	}
	hashed, err := bcrypt.GenerateFromPassword([]byte(password), DefaultBcryptCost)
	if err != nil {
		return "", fmt.Errorf("failed to hash password: %w", err)
	}
	return string(hashed), nil
}

// CheckPassword verifies a plaintext password against a bcrypt hash in constant time.
func CheckPassword(password, hash string) bool {
	if password == "" || hash == "" {
		return false
	}
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}
