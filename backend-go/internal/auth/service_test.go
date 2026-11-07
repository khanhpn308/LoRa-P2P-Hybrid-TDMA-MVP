package auth_test

import (
	"context"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func setupTestAuthService(t *testing.T) (*auth.Service, auth.UserRepository) {
	t.Helper()
	repo := auth.NewInMemoryUserRepository()
	key := []byte("01234567890123456789012345678901")
	jwtSvc, err := auth.NewJWTService(key)
	if err != nil {
		t.Fatalf("failed to create jwt service: %v", err)
	}
	ticketStore := auth.NewTicketStore()
	svc := auth.NewService(repo, jwtSvc, ticketStore)
	return svc, repo
}

func TestService_Login(t *testing.T) {
	svc, repo := setupTestAuthService(t)
	ctx := context.Background()

	// Seed active user
	hash, err := auth.HashPassword("$ValidPassword123")
	if err != nil {
		t.Fatalf("failed to hash password: %v", err)
	}
	activeUser := &auth.User{
		Username:     "active_user",
		PasswordHash: hash,
		Role:         auth.RoleOperator,
		IsActive:     true,
	}
	if err := repo.CreateUser(ctx, activeUser); err != nil {
		t.Fatalf("failed to create active user: %v", err)
	}

	// Seed inactive user
	inactiveUser := &auth.User{
		Username:     "inactive_user",
		PasswordHash: hash,
		Role:         auth.RoleViewer,
		IsActive:     false,
	}
	if err := repo.CreateUser(ctx, inactiveUser); err != nil {
		t.Fatalf("failed to create inactive user: %v", err)
	}

	tests := []struct {
		name        string
		req         auth.LoginRequestDTO
		expectError bool
		expectRole  auth.Role
	}{
		{
			name: "successful login",
			req: auth.LoginRequestDTO{
				Username: "active_user",
				Password: "$ValidPassword123",
			},
			expectError: false,
			expectRole:  auth.RoleOperator,
		},
		{
			name: "wrong password",
			req: auth.LoginRequestDTO{
				Username: "active_user",
				Password: "$WrongPassword999",
			},
			expectError: true,
		},
		{
			name: "inactive account",
			req: auth.LoginRequestDTO{
				Username: "inactive_user",
				Password: "$ValidPassword123",
			},
			expectError: true,
		},
		{
			name: "nonexistent user",
			req: auth.LoginRequestDTO{
				Username: "unknown_user",
				Password: "$ValidPassword123",
			},
			expectError: true,
		},
		{
			name: "empty username",
			req: auth.LoginRequestDTO{
				Username: "",
				Password: "$ValidPassword123",
			},
			expectError: true,
		},
		{
			name: "empty password",
			req: auth.LoginRequestDTO{
				Username: "active_user",
				Password: "",
			},
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp, err := svc.Login(ctx, tt.req)
			if tt.expectError {
				if err == nil {
					t.Fatalf("expected error for case %q, got nil", tt.name)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if resp.TokenType != "Bearer" {
				t.Errorf("expected token_type Bearer, got %q", resp.TokenType)
			}
			if resp.ExpiresIn != 3600 {
				t.Errorf("expected expires_in 3600, got %d", resp.ExpiresIn)
			}
			if resp.Role != tt.expectRole {
				t.Errorf("expected role %s, got %s", tt.expectRole, resp.Role)
			}
			if resp.AccessToken == "" {
				t.Error("expected non-empty access token")
			}
		})
	}
}

func TestService_WsTicket(t *testing.T) {
	svc, _ := setupTestAuthService(t)
	ctx := context.Background()

	claims := &auth.Claims{
		Sub:      "user-001",
		Username: "operator",
		Role:     auth.RoleOperator,
		Iat:      time.Now().Unix(),
		Exp:      time.Now().Add(1 * time.Hour).Unix(),
	}

	ticketResp, err := svc.IssueWsTicket(ctx, claims)
	if err != nil {
		t.Fatalf("failed to issue ws ticket: %v", err)
	}
	if ticketResp.Ticket == "" || ticketResp.ExpiresIn != 30 {
		t.Fatalf("invalid ticket response: %+v", ticketResp)
	}

	// Consume ticket
	consumed, ok := svc.ConsumeWsTicket(ticketResp.Ticket)
	if !ok || consumed == nil {
		t.Fatal("expected successful consumption of ticket")
	}
	if consumed.Sub != claims.Sub || consumed.Role != claims.Role {
		t.Fatalf("consumed claims mismatch: %+v", consumed)
	}

	// Replay must fail
	consumedSecond, okSecond := svc.ConsumeWsTicket(ticketResp.Ticket)
	if okSecond || consumedSecond != nil {
		t.Fatal("expected second consumption of same ticket to fail")
	}
}
