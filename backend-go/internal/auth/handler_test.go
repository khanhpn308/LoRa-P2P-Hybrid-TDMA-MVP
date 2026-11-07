package auth_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func setupTestHandler(t *testing.T) (*auth.Handler, *auth.Service, auth.UserRepository) {
	t.Helper()
	repo := auth.NewInMemoryUserRepository()
	key := []byte("01234567890123456789012345678901") // 32 bytes
	jwtSvc, err := auth.NewJWTService(key)
	if err != nil {
		t.Fatalf("failed to create jwt service: %v", err)
	}
	ticketStore := auth.NewTicketStore()
	svc := auth.NewService(repo, jwtSvc, ticketStore)
	handler := auth.NewHandler(svc)
	return handler, svc, repo
}

func TestHandler_Login(t *testing.T) {
	handler, _, repo := setupTestHandler(t)
	ctx := context.Background()

	// Seed test user
	hash, err := auth.HashPassword("$StrongP@ss123")
	if err != nil {
		t.Fatalf("failed to hash password: %v", err)
	}
	err = repo.CreateUser(ctx, &auth.User{
		Username:     "testadmin",
		PasswordHash: hash,
		Role:         auth.RoleAdmin,
		IsActive:     true,
	})
	if err != nil {
		t.Fatalf("failed to create user: %v", err)
	}

	// Seed inactive user
	err = repo.CreateUser(ctx, &auth.User{
		Username:     "disabled_user",
		PasswordHash: hash,
		Role:         auth.RoleOperator,
		IsActive:     false,
	})
	if err != nil {
		t.Fatalf("failed to create inactive user: %v", err)
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	tests := []struct {
		name           string
		body           string
		expectedStatus int
		checkResponse  bool
	}{
		{
			name:           "successful login",
			body:           `{"username":"testadmin","password":"$StrongP@ss123"}`,
			expectedStatus: http.StatusOK,
			checkResponse:  true,
		},
		{
			name:           "wrong password",
			body:           `{"username":"testadmin","password":"$WrongPassword123"}`,
			expectedStatus: http.StatusUnauthorized,
			checkResponse:  false,
		},
		{
			name:           "disabled user account",
			body:           `{"username":"disabled_user","password":"$StrongP@ss123"}`,
			expectedStatus: http.StatusUnauthorized,
			checkResponse:  false,
		},
		{
			name:           "nonexistent user",
			body:           `{"username":"ghost","password":"$StrongP@ss123"}`,
			expectedStatus: http.StatusUnauthorized,
			checkResponse:  false,
		},
		{
			name:           "empty username",
			body:           `{"username":"","password":"$StrongP@ss123"}`,
			expectedStatus: http.StatusBadRequest,
			checkResponse:  false,
		},
		{
			name:           "empty password",
			body:           `{"username":"testadmin","password":""}`,
			expectedStatus: http.StatusBadRequest,
			checkResponse:  false,
		},
		{
			name:           "malformed json",
			body:           `{invalid-json}`,
			expectedStatus: http.StatusBadRequest,
			checkResponse:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("POST", "/api/v1/auth/login", bytes.NewBufferString(tt.body))
			req.Header.Set("Content-Type", "application/json")
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Fatalf("expected status %d, got %d (body: %s)", tt.expectedStatus, rec.Code, rec.Body.String())
			}

			if tt.checkResponse {
				var tokenResp auth.TokenResponseDTO
				if err := json.Unmarshal(rec.Body.Bytes(), &tokenResp); err != nil {
					t.Fatalf("failed to decode login response: %v", err)
				}
				if tokenResp.AccessToken == "" {
					t.Error("expected non-empty access_token")
				}
				if tokenResp.TokenType != "Bearer" {
					t.Errorf("expected token_type Bearer, got %q", tokenResp.TokenType)
				}
				if tokenResp.ExpiresIn != 3600 {
					t.Errorf("expected expires_in 3600, got %d", tokenResp.ExpiresIn)
				}
				if tokenResp.Role != auth.RoleAdmin {
					t.Errorf("expected role ADMIN, got %s", tokenResp.Role)
				}
			}
		})
	}
}

func TestHandler_WsTicket(t *testing.T) {
	handler, svc, _ := setupTestHandler(t)

	// Issue valid token for operator
	operatorUser := &auth.User{
		ID:       "user-op-1",
		Username: "operator",
		Role:     auth.RoleOperator,
		IsActive: true,
	}
	validToken, err := svc.JWTService().GenerateToken(operatorUser, 1*time.Hour)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	expiredToken, err := svc.JWTService().GenerateToken(operatorUser, -1*time.Minute)
	if err != nil {
		t.Fatalf("failed to generate expired token: %v", err)
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	tests := []struct {
		name           string
		authHeader     string
		expectedStatus int
		expectTicket   bool
	}{
		{
			name:           "valid bearer token gets ticket",
			authHeader:     "Bearer " + validToken,
			expectedStatus: http.StatusOK,
			expectTicket:   true,
		},
		{
			name:           "missing authorization header",
			authHeader:     "",
			expectedStatus: http.StatusUnauthorized,
			expectTicket:   false,
		},
		{
			name:           "empty bearer token",
			authHeader:     "Bearer ",
			expectedStatus: http.StatusUnauthorized,
			expectTicket:   false,
		},
		{
			name:           "expired bearer token",
			authHeader:     "Bearer " + expiredToken,
			expectedStatus: http.StatusUnauthorized,
			expectTicket:   false,
		},
		{
			name:           "invalid bearer token signature",
			authHeader:     "Bearer " + validToken + "invalid",
			expectedStatus: http.StatusUnauthorized,
			expectTicket:   false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("POST", "/api/v1/auth/ws-ticket", nil)
			if tt.authHeader != "" {
				req.Header.Set("Authorization", tt.authHeader)
			}
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Fatalf("expected status %d, got %d (body: %s)", tt.expectedStatus, rec.Code, rec.Body.String())
			}

			if tt.expectTicket {
				var ticketResp auth.WsTicketResponseDTO
				if err := json.Unmarshal(rec.Body.Bytes(), &ticketResp); err != nil {
					t.Fatalf("failed to decode ws-ticket response: %v", err)
				}
				if ticketResp.Ticket == "" {
					t.Error("expected non-empty ticket")
				}
				if ticketResp.ExpiresIn != 30 {
					t.Errorf("expected expires_in 30, got %d", ticketResp.ExpiresIn)
				}

				// Consume ticket through service
				claims, ok := svc.ConsumeWsTicket(ticketResp.Ticket)
				if !ok || claims == nil {
					t.Fatal("first consumption of issued ticket must succeed")
				}
				if claims.Role != auth.RoleOperator {
					t.Errorf("expected role OPERATOR, got %s", claims.Role)
				}

				// Second consumption must fail
				secondClaims, secondOk := svc.ConsumeWsTicket(ticketResp.Ticket)
				if secondOk || secondClaims != nil {
					t.Fatal("second consumption of issued ticket must fail (replay protection)")
				}
			}
		})
	}
}
