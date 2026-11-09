package auth

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

// DefaultTokenDuration defines the standard 60-minute JWT token lifetime (ADR-0005).
const DefaultTokenDuration = 60 * time.Minute

// DefaultTicketTTL defines the standard 30-second single-use WebSocket ticket lifetime (ADR-0005).
const DefaultTicketTTL = 30 * time.Second

// Dummy bcrypt hash for constant-time comparison against nonexistent users (defends against timing user enumeration).
var dummyBcryptHash = "$2a$12$e80yVvX7WzG7/gQ4n1K13.xK3m1p1K13.xK3m1p1K13.xK3m1p1K"

// Service provides high-level authentication, token management, and WebSocket handshake workflows.
type Service struct {
	repo        UserRepository
	jwtService  *JWTService
	ticketStore *TicketStore
}

// NewService constructs a new auth Service.
func NewService(repo UserRepository, jwtService *JWTService, ticketStore *TicketStore) *Service {
	return &Service{
		repo:        repo,
		jwtService:  jwtService,
		ticketStore: ticketStore,
	}
}

// Login authenticates user credentials, checks account status, and issues a 60-minute HS256 Bearer JWT.
// To prevent user enumeration attacks, it returns a generic ErrInvalidCredentials for both nonexistent users
// and mismatched passwords, with equalized execution timing.
func (s *Service) Login(ctx context.Context, req LoginRequestDTO) (*TokenResponseDTO, error) {
	if req.Username == "" || req.Password == "" {
		return nil, fmt.Errorf("%w: username and password cannot be empty", ErrInvalidCredentials)
	}

	user, err := s.repo.GetByUsername(ctx, req.Username)
	if err != nil {
		if errors.Is(err, ErrUserNotFound) {
			// Perform dummy hash comparison to defend against timing-based user enumeration
			CheckPassword(req.Password, dummyBcryptHash)
			return nil, ErrInvalidCredentials
		}
		return nil, fmt.Errorf("login failed: %w", err)
	}

	if !user.IsActive {
		// Run dummy comparison to equalize execution time
		CheckPassword(req.Password, dummyBcryptHash)
		return nil, ErrUserInactive
	}

	if !CheckPassword(req.Password, user.PasswordHash) {
		return nil, ErrInvalidCredentials
	}

	token, err := s.jwtService.GenerateToken(user, DefaultTokenDuration)
	if err != nil {
		return nil, fmt.Errorf("failed to issue access token: %w", err)
	}

	return &TokenResponseDTO{
		AccessToken: token,
		TokenType:   "Bearer",
		ExpiresIn:   int(DefaultTokenDuration.Seconds()),
		Role:        user.Role,
	}, nil
}

// IssueWsTicket generates an atomic single-use ticket valid for 30 seconds for WebSocket connection establishment.
func (s *Service) IssueWsTicket(ctx context.Context, claims *Claims) (*WsTicketResponseDTO, error) {
	if claims == nil {
		return nil, errors.New("claims cannot be nil")
	}
	if !IsValidRole(claims.Role) {
		return nil, fmt.Errorf("%w: role %s", ErrInsufficientRole, claims.Role)
	}

	ticket, err := s.ticketStore.CreateTicket(*claims, DefaultTicketTTL)
	if err != nil {
		return nil, fmt.Errorf("failed to generate ws ticket: %w", err)
	}

	return &WsTicketResponseDTO{
		Ticket:    ticket,
		ExpiresIn: int(DefaultTicketTTL.Seconds()),
	}, nil
}

// ConsumeWsTicket atomically consumes a WebSocket ticket. Returns claims and true on success, or nil and false.
func (s *Service) ConsumeWsTicket(ticket string) (*Claims, bool) {
	if s.ticketStore == nil {
		return nil, false
	}
	return s.ticketStore.ConsumeTicket(ticket)
}

// ListUsers retrieves all registered user profiles without secrets.
func (s *Service) ListUsers(ctx context.Context) ([]*User, error) {
	return s.repo.ListUsers(ctx)
}

// CreateUser registers a new user with hashed credentials and assigned RBAC role.
func (s *Service) CreateUser(ctx context.Context, req CreateUserRequestDTO) (*User, error) {
	req.Username = strings.TrimSpace(req.Username)
	if req.Username == "" || len(req.Username) > 64 {
		return nil, fmt.Errorf("%w: username must be between 1 and 64 characters", ErrInvalidCredentials)
	}

	if len(req.Password) < 8 || len(req.Password) > 128 {
		return nil, fmt.Errorf("%w: password must be between 8 and 128 characters", ErrInvalidCredentials)
	}

	if req.Role == "" {
		req.Role = RoleOperator
	}
	if !IsValidRole(req.Role) {
		return nil, fmt.Errorf("%w: invalid role %s", ErrInsufficientRole, req.Role)
	}

	existing, err := s.repo.GetByUsername(ctx, req.Username)
	if err == nil && existing != nil {
		return nil, ErrUserAlreadyExists
	}
	if err != nil && !errors.Is(err, ErrUserNotFound) {
		return nil, fmt.Errorf("failed to verify username availability: %w", err)
	}

	hashedPassword, err := HashPassword(req.Password)
	if err != nil {
		return nil, fmt.Errorf("failed to hash password: %w", err)
	}

	newUser := &User{
		Username:     req.Username,
		FullName:     strings.TrimSpace(req.FullName),
		Email:        strings.TrimSpace(req.Email),
		PasswordHash: hashedPassword,
		Role:         req.Role,
		IsActive:     true,
	}

	if err := s.repo.CreateUser(ctx, newUser); err != nil {
		return nil, fmt.Errorf("failed to create user in repository: %w", err)
	}

	return newUser, nil
}

// GetUser retrieves a user profile by UUID or username.
func (s *Service) GetUser(ctx context.Context, idOrUsername string) (*User, error) {
	idOrUsername = strings.TrimSpace(idOrUsername)
	if idOrUsername == "" {
		return nil, ErrUserNotFound
	}

	// 1. Try finding by ID
	user, err := s.repo.GetByID(ctx, idOrUsername)
	if err == nil && user != nil {
		return user, nil
	}

	// 2. Fall back to username
	user, err = s.repo.GetByUsername(ctx, idOrUsername)
	if err == nil && user != nil {
		return user, nil
	}

	return nil, ErrUserNotFound
}

// UpdateUser updates user profile fields (full name, email, role, is_active).
func (s *Service) UpdateUser(ctx context.Context, idOrUsername string, req UpdateUserRequestDTO) (*User, error) {
	idOrUsername = strings.TrimSpace(idOrUsername)
	if idOrUsername == "" {
		return nil, ErrUserNotFound
	}

	user, err := s.GetUser(ctx, idOrUsername)
	if err != nil {
		return nil, err
	}

	if req.Role != nil {
		if !IsValidRole(*req.Role) {
			return nil, fmt.Errorf("%w: invalid role %s", ErrInsufficientRole, *req.Role)
		}
	}

	if req.FullName != nil {
		trimmed := strings.TrimSpace(*req.FullName)
		req.FullName = &trimmed
	}
	if req.Email != nil {
		trimmed := strings.TrimSpace(*req.Email)
		req.Email = &trimmed
	}

	return s.repo.UpdateUser(ctx, user.ID, req)
}

// UpdatePassword hashes and updates the password for a user.
func (s *Service) UpdatePassword(ctx context.Context, idOrUsername string, newPassword string) error {
	idOrUsername = strings.TrimSpace(idOrUsername)
	if idOrUsername == "" {
		return ErrUserNotFound
	}

	user, err := s.GetUser(ctx, idOrUsername)
	if err != nil {
		return err
	}

	if len(newPassword) < 8 || len(newPassword) > 128 {
		return fmt.Errorf("%w: password must be between 8 and 128 characters", ErrInvalidCredentials)
	}

	hashedPassword, err := HashPassword(newPassword)
	if err != nil {
		return fmt.Errorf("failed to hash password: %w", err)
	}

	return s.repo.UpdatePassword(ctx, user.ID, hashedPassword)
}

// JWTService returns the underlying JWTService.
func (s *Service) JWTService() *JWTService {
	return s.jwtService
}

// TicketStore returns the underlying TicketStore.
func (s *Service) TicketStore() *TicketStore {
	return s.ticketStore
}
