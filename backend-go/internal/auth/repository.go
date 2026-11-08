package auth

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth/bcrypt"
)

// UserRepository specifies data access operations for user credentials and RBAC profiles.
type UserRepository interface {
	GetByUsername(ctx context.Context, username string) (*User, error)
	GetByID(ctx context.Context, id string) (*User, error)
	CreateUser(ctx context.Context, user *User) error
	ListUsers(ctx context.Context) ([]*User, error)
}

// PostgresUserRepository implements UserRepository against a live PostgreSQL database (DB-001, DB-002).
type PostgresUserRepository struct {
	db *sql.DB
}

// NewPostgresUserRepository initializes a PostgresUserRepository.
func NewPostgresUserRepository(db *sql.DB) *PostgresUserRepository {
	return &PostgresUserRepository{db: db}
}

// GetByUsername retrieves a user by exact username.
func (r *PostgresUserRepository) GetByUsername(ctx context.Context, username string) (*User, error) {
	const query = `
		SELECT id, username, password_hash, role, is_active, created_at, updated_at
		FROM users
		WHERE username = $1
	`
	var u User
	var roleStr string
	err := r.db.QueryRowContext(ctx, query, username).Scan(
		&u.ID,
		&u.Username,
		&u.PasswordHash,
		&roleStr,
		&u.IsActive,
		&u.CreatedAt,
		&u.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrUserNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query user by username: %w", err)
	}
	u.Role = Role(roleStr)
	return &u, nil
}

// GetByID retrieves a user by UUID.
func (r *PostgresUserRepository) GetByID(ctx context.Context, id string) (*User, error) {
	const query = `
		SELECT id, username, password_hash, role, is_active, created_at, updated_at
		FROM users
		WHERE id = $1
	`
	var u User
	var roleStr string
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&u.ID,
		&u.Username,
		&u.PasswordHash,
		&roleStr,
		&u.IsActive,
		&u.CreatedAt,
		&u.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrUserNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query user by id: %w", err)
	}
	u.Role = Role(roleStr)
	return &u, nil
}

// CreateUser persists a new user into the database using parameterized queries (DB-002).
func (r *PostgresUserRepository) CreateUser(ctx context.Context, user *User) error {
	if user == nil {
		return errors.New("user cannot be nil")
	}
	const query = `
		INSERT INTO users (username, password_hash, role, is_active)
		VALUES ($1, $2, $3, $4)
		RETURNING id, created_at, updated_at
	`
	err := r.db.QueryRowContext(ctx, query, user.Username, user.PasswordHash, string(user.Role), user.IsActive).Scan(
		&user.ID,
		&user.CreatedAt,
		&user.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("failed to insert user record: %w", err)
	}
	return nil
}

// ListUsers queries all users from PostgreSQL.
func (r *PostgresUserRepository) ListUsers(ctx context.Context) ([]*User, error) {
	const query = `
		SELECT id, username, password_hash, role, is_active, created_at, updated_at
		FROM users
		ORDER BY created_at ASC
	`
	rows, err := r.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to list users: %w", err)
	}
	defer rows.Close()

	var users []*User
	for rows.Next() {
		var u User
		var roleStr string
		if err := rows.Scan(
			&u.ID,
			&u.Username,
			&u.PasswordHash,
			&roleStr,
			&u.IsActive,
			&u.CreatedAt,
			&u.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan user row: %w", err)
		}
		u.Role = Role(roleStr)
		users = append(users, &u)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error reading users: %w", err)
	}
	return users, nil
}

// InMemoryUserRepository provides a concurrent thread-safe mock implementation for unit tests (TS-001).
type InMemoryUserRepository struct {
	mu    sync.RWMutex
	users map[string]*User
}

// NewInMemoryUserRepository initializes an empty InMemoryUserRepository.
func NewInMemoryUserRepository() *InMemoryUserRepository {
	return &InMemoryUserRepository{
		users: make(map[string]*User),
	}
}

// GetByUsername retrieves a user by username from the in-memory store.
func (m *InMemoryUserRepository) GetByUsername(ctx context.Context, username string) (*User, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	user, ok := m.users[username]
	if !ok {
		return nil, ErrUserNotFound
	}
	copyUser := *user
	return &copyUser, nil
}

// GetByID retrieves a user by ID from the in-memory store.
func (m *InMemoryUserRepository) GetByID(ctx context.Context, id string) (*User, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	for _, user := range m.users {
		if user.ID == id {
			copyUser := *user
			return &copyUser, nil
		}
	}
	return nil, ErrUserNotFound
}

// CreateUser adds a user into the in-memory store.
func (m *InMemoryUserRepository) CreateUser(ctx context.Context, user *User) error {
	if user == nil {
		return errors.New("user cannot be nil")
	}
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.users[user.Username]; exists {
		return errors.New("username already exists")
	}

	if user.ID == "" {
		user.ID = fmt.Sprintf("user-%d", len(m.users)+1)
	}
	now := time.Now().UTC()
	user.CreatedAt = now
	user.UpdatedAt = now

	copyUser := *user
	m.users[user.Username] = &copyUser
	return nil
}

// ListUsers returns all users in the in-memory store.
func (m *InMemoryUserRepository) ListUsers(ctx context.Context) ([]*User, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var users []*User
	for _, u := range m.users {
		copyUser := *u
		users = append(users, &copyUser)
	}
	return users, nil
}

// SeedUser seeds an account if it does not already exist.
func SeedUser(ctx context.Context, repo UserRepository, username, password string, role Role) (*User, error) {
	existing, err := repo.GetByUsername(ctx, username)
	if err == nil && existing != nil {
		return existing, nil
	}
	if err != nil && !errors.Is(err, ErrUserNotFound) {
		return nil, fmt.Errorf("failed to check existing user %s: %w", username, err)
	}

	var hashedPassword string
	if len(password) < 8 {
		h, err := bcrypt.GenerateFromPassword([]byte(password), DefaultBcryptCost)
		if err != nil {
			return nil, fmt.Errorf("failed to hash password for %s: %w", username, err)
		}
		hashedPassword = string(h)
	} else {
		h, err := HashPassword(password)
		if err != nil {
			return nil, fmt.Errorf("failed to hash password for %s: %w", username, err)
		}
		hashedPassword = h
	}

	newUser := &User{
		Username:     username,
		PasswordHash: hashedPassword,
		Role:         role,
		IsActive:     true,
	}

	if err := repo.CreateUser(ctx, newUser); err != nil {
		return nil, fmt.Errorf("failed to create user %s: %w", username, err)
	}
	return newUser, nil
}

// SeedDefaultUsers seeds default accounts (admin, operator01, viewer01).
func SeedDefaultUsers(ctx context.Context, repo UserRepository) error {
	seeds := []struct {
		username string
		password string
		role     Role
	}{
		{"admin", "admin", RoleAdmin},
		{"operator01", "operator", RoleOperator},
		{"viewer01", "viewer", RoleViewer},
	}

	for _, s := range seeds {
		if _, err := SeedUser(ctx, repo, s.username, s.password, s.role); err != nil {
			return err
		}
	}
	return nil
}

// SeedDefaultAdmin creates a default administrator account if none exists.
func SeedDefaultAdmin(ctx context.Context, repo UserRepository, password string) (*User, error) {
	return SeedUser(ctx, repo, "admin", password, RoleAdmin)
}
