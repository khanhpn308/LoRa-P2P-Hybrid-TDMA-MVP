package auth_test

import (
	"encoding/base64"
	"strings"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func TestNewJWTService_KeyLength(t *testing.T) {
	tests := []struct {
		name        string
		keySize     int
		expectError bool
	}{
		{
			name:        "key size 32 bytes (256 bits)",
			keySize:     32,
			expectError: false,
		},
		{
			name:        "key size 64 bytes (512 bits)",
			keySize:     64,
			expectError: false,
		},
		{
			name:        "key size 31 bytes (too short)",
			keySize:     31,
			expectError: true,
		},
		{
			name:        "empty key",
			keySize:     0,
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			key := make([]byte, tt.keySize)
			svc, err := auth.NewJWTService(key)
			if tt.expectError {
				if err == nil {
					t.Fatalf("expected error for key size %d, got nil", tt.keySize)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if svc == nil {
				t.Fatal("expected non-nil JWTService")
			}
		})
	}
}

func TestJWTService_TokenLifecycle(t *testing.T) {
	key := []byte("01234567890123456789012345678901") // 32 bytes
	svc, err := auth.NewJWTService(key)
	if err != nil {
		t.Fatalf("failed to create jwt service: %v", err)
	}

	user := &auth.User{
		ID:       "550e8400-e29b-41d4-a716-446655440000",
		Username: "operator01",
		Role:     auth.RoleOperator,
		IsActive: true,
	}

	token, err := svc.GenerateToken(user, 1*time.Hour)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	claims, err := svc.VerifyToken(token)
	if err != nil {
		t.Fatalf("failed to verify valid token: %v", err)
	}

	if claims.Sub != user.ID {
		t.Errorf("expected Sub %q, got %q", user.ID, claims.Sub)
	}
	if claims.Username != user.Username {
		t.Errorf("expected Username %q, got %q", user.Username, claims.Username)
	}
	if claims.Role != user.Role {
		t.Errorf("expected Role %q, got %q", user.Role, claims.Role)
	}
	if claims.Exp <= claims.Iat {
		t.Errorf("expected Exp (%d) > Iat (%d)", claims.Exp, claims.Iat)
	}
}

func TestJWTService_TamperedToken(t *testing.T) {
	key := []byte("01234567890123456789012345678901")
	svc, err := auth.NewJWTService(key)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	user := &auth.User{
		ID:       "550e8400-e29b-41d4-a716-446655440000",
		Username: "viewer01",
		Role:     auth.RoleViewer,
		IsActive: true,
	}

	token, err := svc.GenerateToken(user, 1*time.Hour)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	// Tamper payload: replace viewer with ADMIN role
	parts := strings.Split(token, ".")
	tamperedPayload := base64.RawURLEncoding.EncodeToString([]byte(`{"sub":"victim","username":"admin","role":"ADMIN","iat":100,"exp":9999999999}`))
	tamperedToken := parts[0] + "." + tamperedPayload + "." + parts[2]

	_, err = svc.VerifyToken(tamperedToken)
	if err == nil {
		t.Fatal("expected signature mismatch error for tampered token, got nil")
	}
}

func TestJWTService_ExpiredToken(t *testing.T) {
	key := []byte("01234567890123456789012345678901")
	svc, err := auth.NewJWTService(key)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	user := &auth.User{
		ID:       "550e8400-e29b-41d4-a716-446655440000",
		Username: "operator01",
		Role:     auth.RoleOperator,
		IsActive: true,
	}

	// Generate already-expired token (-10 seconds duration)
	token, err := svc.GenerateToken(user, -10*time.Second)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	_, err = svc.VerifyToken(token)
	if err == nil {
		t.Fatal("expected ErrTokenExpired for expired token, got nil")
	}
	if !strings.Contains(err.Error(), "expired") {
		t.Fatalf("expected error mentioning expired, got: %v", err)
	}
}

func TestJWTService_MalformedTokens(t *testing.T) {
	key := []byte("01234567890123456789012345678901")
	svc, err := auth.NewJWTService(key)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	malformed := []string{
		"",
		"part1.part2",
		"part1.part2.part3.part4",
		"invalid-base64.invalid-base64.invalid-base64",
		base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"none","typ":"JWT"}`)) + ".eyJuYW1lIjoidGVzdCJ9.sig",
	}

	for _, token := range malformed {
		t.Run(token, func(t *testing.T) {
			_, err := svc.VerifyToken(token)
			if err == nil {
				t.Fatalf("expected error for malformed token %q, got nil", token)
			}
		})
	}
}
