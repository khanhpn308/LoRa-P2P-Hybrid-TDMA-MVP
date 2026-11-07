package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// JWTService manages the issuance and verification of HS256 Bearer JWTs according to ADR-0005.
type JWTService struct {
	secretKey []byte
}

// NewJWTService initializes a JWTService ensuring a minimum 256-bit (32 bytes) secret key (SE-003).
func NewJWTService(secretKey []byte) (*JWTService, error) {
	if len(secretKey) < 32 {
		return nil, fmt.Errorf("%w: got %d bytes, require >= 32 bytes", ErrInvalidSecretKey, len(secretKey))
	}
	keyCopy := make([]byte, len(secretKey))
	copy(keyCopy, secretKey)
	return &JWTService{
		secretKey: keyCopy,
	}, nil
}

type jwtHeader struct {
	Alg string `json:"alg"`
	Typ string `json:"typ"`
}

// GenerateToken generates a signed HS256 JWT access token with the specified duration.
func (s *JWTService) GenerateToken(user *User, duration time.Duration) (string, error) {
	if user == nil {
		return "", fmt.Errorf("user cannot be nil")
	}
	if !IsValidRole(user.Role) {
		return "", fmt.Errorf("%w: %s", ErrInsufficientRole, user.Role)
	}

	now := time.Now().UTC()
	claims := Claims{
		Sub:      user.ID,
		Username: user.Username,
		Role:     user.Role,
		Iat:      now.Unix(),
		Exp:      now.Add(duration).Unix(),
	}

	header := jwtHeader{
		Alg: "HS256",
		Typ: "JWT",
	}

	headerJSON, err := json.Marshal(header)
	if err != nil {
		return "", fmt.Errorf("failed to encode jwt header: %w", err)
	}

	claimsJSON, err := json.Marshal(claims)
	if err != nil {
		return "", fmt.Errorf("failed to encode jwt claims: %w", err)
	}

	headerB64 := base64.RawURLEncoding.EncodeToString(headerJSON)
	claimsB64 := base64.RawURLEncoding.EncodeToString(claimsJSON)

	signingInput := headerB64 + "." + claimsB64
	sig := s.computeHMAC(signingInput)
	sigB64 := base64.RawURLEncoding.EncodeToString(sig)

	return signingInput + "." + sigB64, nil
}

// VerifyToken parses, cryptographically verifies, and returns validated claims from a JWT string.
func (s *JWTService) VerifyToken(tokenString string) (*Claims, error) {
	parts := strings.Split(tokenString, ".")
	if len(parts) != 3 {
		return nil, ErrInvalidToken
	}

	headerBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return nil, fmt.Errorf("%w: invalid header encoding", ErrInvalidToken)
	}

	var header jwtHeader
	if err := json.Unmarshal(headerBytes, &header); err != nil {
		return nil, fmt.Errorf("%w: malformed header json", ErrInvalidToken)
	}
	if header.Alg != "HS256" || header.Typ != "JWT" {
		return nil, fmt.Errorf("%w: unsupported algorithm or token type", ErrInvalidToken)
	}

	signingInput := parts[0] + "." + parts[1]
	expectedSig := s.computeHMAC(signingInput)

	actualSig, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return nil, fmt.Errorf("%w: invalid signature encoding", ErrInvalidToken)
	}

	// Constant-time HMAC comparison to prevent timing attacks (SE-003)
	if !hmac.Equal(actualSig, expectedSig) {
		return nil, fmt.Errorf("%w: signature mismatch", ErrInvalidToken)
	}

	claimsBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, fmt.Errorf("%w: invalid claims encoding", ErrInvalidToken)
	}

	var claims Claims
	if err := json.Unmarshal(claimsBytes, &claims); err != nil {
		return nil, fmt.Errorf("%w: malformed claims json", ErrInvalidToken)
	}

	if !IsValidRole(claims.Role) {
		return nil, fmt.Errorf("%w: invalid role in claims", ErrInvalidToken)
	}

	now := time.Now().UTC().Unix()
	if now > claims.Exp {
		return nil, ErrTokenExpired
	}

	return &claims, nil
}

func (s *JWTService) computeHMAC(data string) []byte {
	h := hmac.New(sha256.New, s.secretKey)
	h.Write([]byte(data))
	return h.Sum(nil)
}
