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

	passFixture := "$ValidPassword123"
	wrongPassFixture := "$WrongPassword999"

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
				Password: passFixture,
			},
			expectError: false,
			expectRole:  auth.RoleOperator,
		},
		{
			name: "wrong password",
			req: auth.LoginRequestDTO{
				Username: "active_user",
				Password: wrongPassFixture,
			},
			expectError: true,
		},
		{
			name: "inactive account",
			req: auth.LoginRequestDTO{
				Username: "inactive_user",
				Password: passFixture,
			},
			expectError: true,
		},
		{
			name: "nonexistent user",
			req: auth.LoginRequestDTO{
				Username: "unknown_user",
				Password: passFixture,
			},
			expectError: true,
		},
		{
			name: "empty username",
			req: auth.LoginRequestDTO{
				Username: "",
				Password: passFixture,
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

func TestService_UpdateUser(t *testing.T) {
	svc, repo := setupTestAuthService(t)
	ctx := context.Background()

	hash, err := auth.HashPassword("$ValidPassword123")
	if err != nil {
		t.Fatalf("failed to hash password: %v", err)
	}

	user := &auth.User{
		ID:           "test-user-01",
		Username:     "update_target",
		FullName:     "Original Name",
		Email:        "original@example.com",
		PasswordHash: hash,
		Role:         auth.RoleViewer,
		IsActive:     true,
	}
	if err := repo.CreateUser(ctx, user); err != nil {
		t.Fatalf("failed to seed user: %v", err)
	}

	// 1. Update full name and email
	newName := "Updated Name"
	newEmail := "updated@example.com"
	updated, err := svc.UpdateUser(ctx, "update_target", auth.UpdateUserRequestDTO{
		FullName: &newName,
		Email:    &newEmail,
	})
	if err != nil {
		t.Fatalf("failed to update user details: %v", err)
	}
	if updated.FullName != newName || updated.Email != newEmail {
		t.Errorf("expected %s, %s; got %s, %s", newName, newEmail, updated.FullName, updated.Email)
	}

	// 2. Update role
	newRole := auth.RoleAdmin
	updated, err = svc.UpdateUser(ctx, "update_target", auth.UpdateUserRequestDTO{
		Role: &newRole,
	})
	if err != nil {
		t.Fatalf("failed to update user role: %v", err)
	}
	if updated.Role != auth.RoleAdmin {
		t.Errorf("expected role ADMIN, got %s", updated.Role)
	}

	// 3. Deactivate user
	inactive := false
	updated, err = svc.UpdateUser(ctx, "update_target", auth.UpdateUserRequestDTO{
		IsActive: &inactive,
	})
	if err != nil {
		t.Fatalf("failed to deactivate user: %v", err)
	}
	if updated.IsActive != false {
		t.Error("expected user to be inactive")
	}

	// 4. Verify login is blocked when inactive
	_, err = svc.Login(ctx, auth.LoginRequestDTO{
		Username: "update_target",
		Password: "$ValidPassword123",
	})
	if err == nil {
		t.Fatal("expected inactive user login to fail, got nil")
	}

	// 5. Reactivate user
	active := true
	updated, err = svc.UpdateUser(ctx, "update_target", auth.UpdateUserRequestDTO{
		IsActive: &active,
	})
	if err != nil {
		t.Fatalf("failed to reactivate user: %v", err)
	}
	if updated.IsActive != true {
		t.Error("expected user to be active")
	}

	// 6. Verify login works again
	loginResp, err := svc.Login(ctx, auth.LoginRequestDTO{
		Username: "update_target",
		Password: "$ValidPassword123",
	})
	if err != nil {
		t.Fatalf("expected login to succeed after reactivation: %v", err)
	}
	if loginResp.AccessToken == "" {
		t.Error("expected non-empty token")
	}

	// 7. Error case: nonexistent user
	_, err = svc.UpdateUser(ctx, "nonexistent_user", auth.UpdateUserRequestDTO{
		FullName: &newName,
	})
	if err == nil {
		t.Fatal("expected error for nonexistent user, got nil")
	}

	// 8. Error case: invalid role
	invalidRole := auth.Role("SUPERUSER")
	_, err = svc.UpdateUser(ctx, "update_target", auth.UpdateUserRequestDTO{
		Role: &invalidRole,
	})
	if err == nil {
		t.Fatal("expected error for invalid role, got nil")
	}
}

func TestService_UpdatePassword(t *testing.T) {
	svc, repo := setupTestAuthService(t)
	ctx := context.Background()

	hash, err := auth.HashPassword("$OldPassword123")
	if err != nil {
		t.Fatalf("failed to hash password: %v", err)
	}

	user := &auth.User{
		ID:           "test-user-pw",
		Username:     "password_target",
		FullName:     "PW Target",
		Email:        "pw@example.com",
		PasswordHash: hash,
		Role:         auth.RoleOperator,
		IsActive:     true,
	}
	if err := repo.CreateUser(ctx, user); err != nil {
		t.Fatalf("failed to seed user: %v", err)
	}

	// 1. Successful password update
	newPass := "$BrandNewP@ssw0rd!"
	if err := svc.UpdatePassword(ctx, "password_target", newPass); err != nil {
		t.Fatalf("failed to update password: %v", err)
	}

	// Old password must fail
	_, err = svc.Login(ctx, auth.LoginRequestDTO{
		Username: "password_target",
		Password: "$OldPassword123",
	})
	if err == nil {
		t.Fatal("expected old password to fail, but it succeeded")
	}

	// New password must succeed
	loginResp, err := svc.Login(ctx, auth.LoginRequestDTO{
		Username: "password_target",
		Password: newPass,
	})
	if err != nil {
		t.Fatalf("expected login with new password to succeed: %v", err)
	}
	if loginResp.AccessToken == "" {
		t.Error("expected valid access token")
	}

	// 2. Too short password (< 8 chars)
	if err := svc.UpdatePassword(ctx, "password_target", "short"); err == nil {
		t.Fatal("expected error for short password, got nil")
	}

	// 3. Nonexistent user
	if err := svc.UpdatePassword(ctx, "ghost_user", "$NewValidPassword123"); err == nil {
		t.Fatal("expected error for nonexistent user, got nil")
	}
}
