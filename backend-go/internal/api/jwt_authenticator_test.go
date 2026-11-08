package api_test

import (
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func TestJWTAuthenticator(t *testing.T) {
	key := []byte("test-jwt-secret-key-at-least-32-bytes!!")
	jwtSvc, err := auth.NewJWTService(key)
	if err != nil {
		t.Fatalf("failed to create JWTService: %v", err)
	}

	authAdapter := api.NewJWTAuthenticator(jwtSvc)

	// Nil authenticator check
	var nilAuth *api.JWTAuthenticator
	if _, err := nilAuth.Authenticate("token"); err == nil {
		t.Error("expected error for nil authenticator")
	}

	// Admin token
	adminUser := &auth.User{ID: "u1", Username: "admin", Role: auth.RoleAdmin}
	adminToken, err := jwtSvc.GenerateToken(adminUser, 1*time.Hour)
	if err != nil {
		t.Fatalf("failed to generate admin token: %v", err)
	}

	role, err := authAdapter.Authenticate(adminToken)
	if err != nil {
		t.Fatalf("unexpected auth error: %v", err)
	}
	if role != api.RoleAdmin {
		t.Errorf("expected RoleAdmin, got %s", role)
	}

	// Operator token
	opUser := &auth.User{ID: "u2", Username: "operator01", Role: auth.RoleOperator}
	opToken, err := jwtSvc.GenerateToken(opUser, 1*time.Hour)
	if err != nil {
		t.Fatalf("failed to generate operator token: %v", err)
	}
	role, err = authAdapter.Authenticate(opToken)
	if err != nil {
		t.Fatalf("unexpected auth error: %v", err)
	}
	if role != api.RoleOperator {
		t.Errorf("expected RoleOperator, got %s", role)
	}

	// Expired token
	expiredToken, err := jwtSvc.GenerateToken(adminUser, -1*time.Minute)
	if err != nil {
		t.Fatalf("failed to generate expired token: %v", err)
	}
	if _, err := authAdapter.Authenticate(expiredToken); err == nil {
		t.Error("expected error for expired token")
	}

	// Invalid token string
	if _, err := authAdapter.Authenticate("invalid.bearer.token"); err == nil {
		t.Error("expected error for invalid token")
	}
}
