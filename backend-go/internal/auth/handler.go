package auth

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
)

const maxPayloadBytes = 4096

// Handler handles HTTP endpoints for user authentication and WebSocket ticket issuance (ADR-0005).
type Handler struct {
	authService *Service
}

// NewHandler constructs an auth Handler.
func NewHandler(authService *Service) *Handler {
	return &Handler{
		authService: authService,
	}
}

// RegisterRoutes registers the authentication and ticket endpoints on http.ServeMux according to OpenAPI 3.0.3 spec.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v1/auth/login", h.handleLogin)
	mux.HandleFunc("POST /api/v1/auth/ws-ticket", h.handleWsTicket)
	mux.HandleFunc("GET /api/v1/users", h.handleListUsers)
	mux.HandleFunc("POST /api/v1/users", h.handleCreateUser)
	mux.HandleFunc("GET /api/v1/users/{id}", h.handleGetUser)
}

func (h *Handler) handleLogin(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
	if err != nil {
		writeAuthError(w, http.StatusBadRequest, "INVALID_BODY", "failed to read request body")
		return
	}

	var req LoginRequestDTO
	if err := json.Unmarshal(body, &req); err != nil {
		writeAuthError(w, http.StatusBadRequest, "MALFORMED_JSON", err.Error())
		return
	}

	req.Username = strings.TrimSpace(req.Username)
	if req.Username == "" || len(req.Username) > 64 {
		writeAuthError(w, http.StatusBadRequest, "INVALID_USERNAME", "username must be between 1 and 64 characters")
		return
	}

	if req.Password == "" || len(req.Password) > 128 {
		writeAuthError(w, http.StatusBadRequest, "INVALID_PASSWORD", "password must be between 1 and 128 characters")
		return
	}

	resp, err := h.authService.Login(r.Context(), req)
	if err != nil {
		if errors.Is(err, ErrInvalidCredentials) || errors.Is(err, ErrUserNotFound) || errors.Is(err, ErrUserInactive) {
			writeAuthError(w, http.StatusUnauthorized, "UNAUTHORIZED", "invalid credentials")
			return
		}
		writeAuthError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "authentication processing failed")
		return
	}

	writeAuthJSON(w, http.StatusOK, resp)
}

func (h *Handler) resolveClaims(w http.ResponseWriter, r *http.Request) (*Claims, bool) {
	claims, ok := ClaimsFromContext(r.Context())
	if ok && claims != nil {
		return claims, true
	}

	authHeader := r.Header.Get("Authorization")
	if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
		w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
		writeAuthError(w, http.StatusUnauthorized, "UNAUTHORIZED", "missing or malformed bearer token")
		return nil, false
	}

	token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
	if token == "" {
		w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
		writeAuthError(w, http.StatusUnauthorized, "UNAUTHORIZED", "empty bearer token")
		return nil, false
	}

	var err error
	claims, err = h.authService.JWTService().VerifyToken(token)
	if err != nil {
		w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
		writeAuthError(w, http.StatusUnauthorized, "UNAUTHORIZED", "invalid or expired token")
		return nil, false
	}

	return claims, true
}

func (h *Handler) handleWsTicket(w http.ResponseWriter, r *http.Request) {
	claims, ok := h.resolveClaims(w, r)
	if !ok {
		return
	}

	// 2. Enforce RBAC: all authenticated roles (ADMIN, OPERATOR, VIEWER) are allowed per OpenAPI x-roles
	if !IsValidRole(claims.Role) {
		writeAuthError(w, http.StatusForbidden, "FORBIDDEN", "unauthorized role for websocket ticket")
		return
	}

	// 3. Issue atomic single-use ticket
	ticketResp, err := h.authService.IssueWsTicket(r.Context(), claims)
	if err != nil {
		writeAuthError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to issue websocket ticket")
		return
	}

	writeAuthJSON(w, http.StatusOK, ticketResp)
}

func (h *Handler) handleListUsers(w http.ResponseWriter, r *http.Request) {
	claims, ok := h.resolveClaims(w, r)
	if !ok {
		return
	}

	if !IsValidRole(claims.Role) {
		writeAuthError(w, http.StatusForbidden, "FORBIDDEN", "unauthorized role")
		return
	}

	users, err := h.authService.ListUsers(r.Context())
	if err != nil {
		writeAuthError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list users")
		return
	}

	if users == nil {
		users = []*User{}
	}

	writeAuthJSON(w, http.StatusOK, users)
}

func (h *Handler) handleCreateUser(w http.ResponseWriter, r *http.Request) {
	claims, ok := h.resolveClaims(w, r)
	if !ok {
		return
	}

	if claims.Role != RoleAdmin {
		writeAuthError(w, http.StatusForbidden, "FORBIDDEN", "only administrators can create users")
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
	if err != nil {
		writeAuthError(w, http.StatusBadRequest, "INVALID_BODY", "failed to read request body")
		return
	}

	var req CreateUserRequestDTO
	if err := json.Unmarshal(body, &req); err != nil {
		writeAuthError(w, http.StatusBadRequest, "MALFORMED_JSON", err.Error())
		return
	}

	req.Username = strings.TrimSpace(req.Username)
	if req.Username == "" || len(req.Username) > 64 {
		writeAuthError(w, http.StatusBadRequest, "INVALID_USERNAME", "username must be between 1 and 64 characters")
		return
	}

	if len(req.Password) < 8 || len(req.Password) > 128 {
		writeAuthError(w, http.StatusBadRequest, "INVALID_PASSWORD", "password must be between 8 and 128 characters")
		return
	}

	if req.Role == "" {
		req.Role = RoleOperator
	}
	if !IsValidRole(req.Role) {
		writeAuthError(w, http.StatusBadRequest, "INVALID_ROLE", "role must be ADMIN, OPERATOR, or VIEWER")
		return
	}

	createdUser, err := h.authService.CreateUser(r.Context(), req)
	if err != nil {
		if errors.Is(err, ErrUserAlreadyExists) {
			writeAuthError(w, http.StatusConflict, "USER_EXISTS", "a user with this username already exists")
			return
		}
		writeAuthError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to create user")
		return
	}

	writeAuthJSON(w, http.StatusCreated, createdUser)
}

func (h *Handler) handleGetUser(w http.ResponseWriter, r *http.Request) {
	claims, ok := h.resolveClaims(w, r)
	if !ok {
		return
	}

	if !IsValidRole(claims.Role) {
		writeAuthError(w, http.StatusForbidden, "FORBIDDEN", "unauthorized role")
		return
	}

	idOrUsername := strings.TrimSpace(r.PathValue("id"))
	if idOrUsername == "" {
		writeAuthError(w, http.StatusBadRequest, "INVALID_ID", "user id or username is required")
		return
	}

	user, err := h.authService.GetUser(r.Context(), idOrUsername)
	if err != nil {
		if errors.Is(err, ErrUserNotFound) {
			writeAuthError(w, http.StatusNotFound, "NOT_FOUND", "user not found")
			return
		}
		writeAuthError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to retrieve user")
		return
	}

	writeAuthJSON(w, http.StatusOK, user)
}

func writeAuthJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}
