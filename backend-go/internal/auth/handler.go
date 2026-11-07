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

func (h *Handler) handleWsTicket(w http.ResponseWriter, r *http.Request) {
	// 1. Resolve caller claims either from context (if AuthMiddleware was executed) or directly from Bearer header
	claims, ok := ClaimsFromContext(r.Context())
	if !ok || claims == nil {
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
			w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
			writeAuthError(w, http.StatusUnauthorized, "UNAUTHORIZED", "missing or malformed bearer token")
			return
		}

		token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
		if token == "" {
			w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
			writeAuthError(w, http.StatusUnauthorized, "UNAUTHORIZED", "empty bearer token")
			return
		}

		var err error
		claims, err = h.authService.JWTService().VerifyToken(token)
		if err != nil {
			w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
			writeAuthError(w, http.StatusUnauthorized, "UNAUTHORIZED", "invalid or expired token")
			return
		}
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

func writeAuthJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}
