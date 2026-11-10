package api

import (
	"errors"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

// JWTAuthenticator authenticates bearer JWT tokens using auth.JWTService and returns the caller's Role.
type JWTAuthenticator struct {
	jwtService *auth.JWTService
}

// NewJWTAuthenticator constructs a new JWTAuthenticator.
func NewJWTAuthenticator(jwtService *auth.JWTService) *JWTAuthenticator {
	return &JWTAuthenticator{jwtService: jwtService}
}

// Authenticate verifies the token signature and expiration, returning the resolved Role.
func (a *JWTAuthenticator) Authenticate(token string) (Role, error) {
	if a == nil || a.jwtService == nil {
		return "", errors.New("unconfigured jwt authenticator")
	}
	claims, err := a.jwtService.VerifyToken(token)
	if err != nil {
		return "", err
	}
	return Role(claims.Role), nil
}

// JWTService returns the underlying auth.JWTService.
func (a *JWTAuthenticator) JWTService() *auth.JWTService {
	if a == nil {
		return nil
	}
	return a.jwtService
}
