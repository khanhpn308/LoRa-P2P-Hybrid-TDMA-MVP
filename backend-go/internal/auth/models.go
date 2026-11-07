package auth

import (
	"errors"
	"time"
)

// Role defines role-based access control roles according to ADR-0005.
type Role string

const (
	// RoleAdmin grants full administrative rights.
	RoleAdmin Role = "ADMIN"
	// RoleOperator grants operational monitoring and execution rights.
	RoleOperator Role = "OPERATOR"
	// RoleViewer grants read-only access.
	RoleViewer Role = "VIEWER"
)

// IsValidRole verifies whether the provided role string is an approved RBAC role.
func IsValidRole(r Role) bool {
	switch r {
	case RoleAdmin, RoleOperator, RoleViewer:
		return true
	default:
		return false
	}
}

// User represents an authenticated principal stored in PostgreSQL.
type User struct {
	ID           string    `json:"id"`
	Username     string    `json:"username"`
	PasswordHash string    `json:"-"`
	Role         Role      `json:"role"`
	IsActive     bool      `json:"is_active"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

// Claims represents JWT payload claims following ADR-0005.
type Claims struct {
	Sub      string `json:"sub"`
	Username string `json:"username"`
	Role     Role   `json:"role"`
	Iat      int64  `json:"iat"`
	Exp      int64  `json:"exp"`
}

// LoginRequestDTO represents the credentials payload for POST /api/v1/auth/login.
type LoginRequestDTO struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// TokenResponseDTO represents the successful authentication response.
type TokenResponseDTO struct {
	AccessToken string `json:"access_token"`
	TokenType   string `json:"token_type"`
	ExpiresIn   int    `json:"expires_in"`
	Role        Role   `json:"role"`
}

// WsTicketResponseDTO represents the single-use ticket response for POST /api/v1/auth/ws-ticket.
type WsTicketResponseDTO struct {
	Ticket    string `json:"ticket"`
	ExpiresIn int    `json:"expires_in"`
}

// Error definitions for authentication and authorization workflows.
var (
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrUserNotFound       = errors.New("user not found")
	ErrUserInactive       = errors.New("user account is inactive")
	ErrTokenExpired       = errors.New("token has expired")
	ErrInvalidToken       = errors.New("invalid token")
	ErrInsufficientRole   = errors.New("insufficient role permissions")
	ErrInvalidSecretKey   = errors.New("jwt secret key must be at least 32 bytes (256 bits)")
	ErrInvalidTicket      = errors.New("invalid or expired websocket ticket")
)
