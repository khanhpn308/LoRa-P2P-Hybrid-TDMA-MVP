package api

import (
	"errors"
)

// Role represents authorization roles for REST API clients.
type Role string

const (
	// RoleAdmin grants full administrative rights, including device provisioning.
	RoleAdmin Role = "ADMIN"
	// RoleOperator grants runtime operational control without provisioning keys.
	RoleOperator Role = "OPERATOR"
	// RoleViewer grants read-only visibility.
	RoleViewer Role = "VIEWER"
)

// Authenticator authenticates bearer tokens and resolves caller roles.
type Authenticator interface {
	Authenticate(token string) (Role, error)
}

// StaticAuthenticator provides a token-to-role lookup map for testing and MVP.
type StaticAuthenticator struct {
	tokens map[string]Role
}

// NewStaticAuthenticator creates a StaticAuthenticator with the provided token map.
func NewStaticAuthenticator(tokens map[string]Role) *StaticAuthenticator {
	return &StaticAuthenticator{tokens: tokens}
}

// Authenticate resolves the role associated with the provided bearer token.
func (a *StaticAuthenticator) Authenticate(token string) (Role, error) {
	if a == nil || a.tokens == nil {
		return "", errors.New("unconfigured authenticator")
	}
	role, ok := a.tokens[token]
	if !ok {
		return "", errors.New("invalid or expired bearer token")
	}
	return role, nil
}
