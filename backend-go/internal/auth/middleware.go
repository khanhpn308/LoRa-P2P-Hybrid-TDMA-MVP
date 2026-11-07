package auth

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
)

type contextKey string

const claimsContextKey contextKey = "auth_claims"

// ContextWithClaims returns a child context populated with authenticated Claims.
func ContextWithClaims(ctx context.Context, claims *Claims) context.Context {
	return context.WithValue(ctx, claimsContextKey, claims)
}

// ClaimsFromContext retrieves authenticated Claims from context if present.
func ClaimsFromContext(ctx context.Context) (*Claims, bool) {
	claims, ok := ctx.Value(claimsContextKey).(*Claims)
	return claims, ok && claims != nil
}

type errorResponse struct {
	Error   string `json:"error"`
	Message string `json:"message"`
}

func writeAuthError(w http.ResponseWriter, status int, errCode, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(errorResponse{
		Error:   errCode,
		Message: message,
	})
}

// AuthMiddleware validates Bearer JWT access tokens and injects verified Claims into request context (SE-006).
func AuthMiddleware(jwtService *JWTService) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
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

			claims, err := jwtService.VerifyToken(token)
			if err != nil {
				w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
				writeAuthError(w, http.StatusUnauthorized, "UNAUTHORIZED", "invalid or expired token")
				return
			}

			ctx := ContextWithClaims(r.Context(), claims)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// RequireRole enforces server-side Role-Based Access Control (RBAC, SE-004).
func RequireRole(roles ...Role) func(http.Handler) http.Handler {
	allowedRoles := make(map[Role]bool, len(roles))
	for _, r := range roles {
		allowedRoles[r] = true
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			claims, ok := ClaimsFromContext(r.Context())
			if !ok || claims == nil {
				writeAuthError(w, http.StatusUnauthorized, "UNAUTHORIZED", "authentication required")
				return
			}

			if !allowedRoles[claims.Role] {
				writeAuthError(w, http.StatusForbidden, "FORBIDDEN", "insufficient role permissions")
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}
