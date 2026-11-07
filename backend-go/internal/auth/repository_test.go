package auth_test

import (
	"context"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func TestInMemoryUserRepository(t *testing.T) {
	repo := auth.NewInMemoryUserRepository()
	ctx := context.Background()

	user := &auth.User{
		Username:     "testuser",
		PasswordHash: "somehash",
		Role:         auth.RoleOperator,
		IsActive:     true,
	}

	if err := repo.CreateUser(ctx, user); err != nil {
		t.Fatalf("failed to create user: %v", err)
	}

	// Fetch by username
	fetched, err := repo.GetByUsername(ctx, "testuser")
	if err != nil {
		t.Fatalf("failed to fetch user: %v", err)
	}
	if fetched.Username != user.Username || fetched.Role != user.Role {
		t.Fatalf("fetched user mismatch: %+v", fetched)
	}

	// Fetch by ID
	fetchedByID, err := repo.GetByID(ctx, fetched.ID)
	if err != nil {
		t.Fatalf("failed to fetch user by id: %v", err)
	}
	if fetchedByID.Username != user.Username {
		t.Fatalf("fetched by ID mismatch: %+v", fetchedByID)
	}

	// Duplicate username should fail
	err = repo.CreateUser(ctx, user)
	if err == nil {
		t.Fatal("expected error on duplicate username, got nil")
	}

	// Non-existent user
	_, err = repo.GetByUsername(ctx, "nonexistent")
	if err == nil {
		t.Fatal("expected error on nonexistent user, got nil")
	}
}

func TestSeedDefaultAdmin(t *testing.T) {
	repo := auth.NewInMemoryUserRepository()
	ctx := context.Background()

	admin, err := auth.SeedDefaultAdmin(ctx, repo, "$AdminSecret123!")
	if err != nil {
		t.Fatalf("failed to seed admin: %v", err)
	}
	if admin.Username != "admin" || admin.Role != auth.RoleAdmin {
		t.Fatalf("admin user profile mismatch: %+v", admin)
	}

	// Calling seed again should be idempotent
	admin2, err := auth.SeedDefaultAdmin(ctx, repo, "$AdminSecret123!")
	if err != nil {
		t.Fatalf("idempotent seed failed: %v", err)
	}
	if admin2.Username != admin.Username {
		t.Fatalf("expected same admin user, got: %+v", admin2)
	}
}
