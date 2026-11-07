package auth_test

import (
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth/bcrypt"
)

func TestPasswordHashing(t *testing.T) {
	tests := []struct {
		name        string
		password    string
		expectError bool
	}{
		{
			name:        "valid 8 character password",
			password:    "$valid08",
			expectError: false,
		},
		{
			name:        "valid complex password",
			password:    "$P@ssw0rdSecure!2026",
			expectError: false,
		},
		{
			name:        "too short password (7 chars)",
			password:    "$short7",
			expectError: true,
		},
		{
			name:        "empty password",
			password:    "",
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			hashed, err := auth.HashPassword(tt.password)
			if tt.expectError {
				if err == nil {
					t.Fatalf("expected error for password %q, got nil", tt.password)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			// Verify bcrypt cost factor is >= 12 (SE-003)
			cost, err := bcrypt.Cost([]byte(hashed))
			if err != nil {
				t.Fatalf("failed to determine bcrypt cost: %v", err)
			}
			if cost < 12 {
				t.Fatalf("expected cost >= 12, got %d", cost)
			}

			// Verify correct match
			if !auth.CheckPassword(tt.password, hashed) {
				t.Fatal("password check failed for valid match")
			}

			// Verify wrong password fails
			if auth.CheckPassword("$WrongPassword123", hashed) {
				t.Fatal("password check succeeded for mismatched password")
			}
		})
	}
}

func TestCheckPassword_EmptyCases(t *testing.T) {
	if auth.CheckPassword("", "$2a$12$somehashhere") {
		t.Fatal("empty password must return false")
	}
	if auth.CheckPassword("$password", "") {
		t.Fatal("empty hash must return false")
	}
}
