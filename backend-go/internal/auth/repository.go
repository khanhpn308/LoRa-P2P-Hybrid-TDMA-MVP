package auth

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"sync"
	"time"
)

// UserRepository specifies data access operations for user credentials and RBAC profiles.
type UserRepository interface {
	GetByUsername(ctx context.Context, username string) (*User, error)
	GetByID(ctx context.Context, id string) (*User, error)
	CreateUser(ctx context.Context, user *User) error
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

// SeedDefaultAdmin creates a default administrator account if none exists.
func SeedDefaultAdmin(ctx context.Context, repo UserRepository, password string) (*User, error) {
	existing, err := repo.GetByUsername(ctx, "admin")
	if err == nil && existing != nil {
		return existing, nil
	}
	if err != nil && !errors.Is(err, ErrUserNotFound) {
		return nil, fmt.Errorf("failed to check existing admin: %w", err)
	}

	hashedPassword, err := HashPassword(password)
	if err != nil {
		return nil, fmt.Errorf("failed to hash admin password: %w", err)
	}

	adminUser := &User{
		Username:     "admin",
		PasswordHash: hashedPassword,
		Role:         RoleAdmin,
		IsActive:     true,
	}

	if err := repo.CreateUser(ctx, adminUser); err != nil {
		return nil, fmt.Errorf("failed to seed admin user: %w", err)
	}
	return adminUser, nil
}
