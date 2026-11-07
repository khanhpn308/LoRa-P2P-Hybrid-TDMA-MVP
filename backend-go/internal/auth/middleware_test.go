package auth_test

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func TestAuthMiddleware(t *testing.T) {
	key := []byte("01234567890123456789012345678901")
	jwtSvc, err := auth.NewJWTService(key)
	if err != nil {
		t.Fatalf("failed to create jwt service: %v", err)
	}

	validUser := &auth.User{
		ID:       "user-1",
		Username: "operator",
		Role:     auth.RoleOperator,
		IsActive: true,
	}
	validToken, err := jwtSvc.GenerateToken(validUser, 1*time.Hour)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	expiredToken, err := jwtSvc.GenerateToken(validUser, -1*time.Minute)
	if err != nil {
		t.Fatalf("failed to generate expired token: %v", err)
	}

	middleware := auth.AuthMiddleware(jwtSvc)
	handlerToWrap := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		claims, ok := auth.ClaimsFromContext(r.Context())
		if !ok || claims == nil {
			t.Error("expected claims in context")
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	wrappedHandler := middleware(handlerToWrap)

	tests := []struct {
		name           string
		authHeader     string
		expectedStatus int
	}{
		{
			name:           "valid bearer token",
			authHeader:     "Bearer " + validToken,
			expectedStatus: http.StatusOK,
		},
		{
			name:           "missing auth header",
			authHeader:     "",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "malformed header prefix",
			authHeader:     "Basic " + validToken,
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "empty bearer token",
			authHeader:     "Bearer ",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "expired token",
			authHeader:     "Bearer " + expiredToken,
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "tampered token",
			authHeader:     "Bearer " + validToken + "corrupted",
			expectedStatus: http.StatusUnauthorized,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", "/test", nil)
			if tt.authHeader != "" {
				req.Header.Set("Authorization", tt.authHeader)
			}
			rec := httptest.NewRecorder()

			wrappedHandler.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Fatalf("expected status %d, got %d (body: %s)", tt.expectedStatus, rec.Code, rec.Body.String())
			}
			if tt.expectedStatus == http.StatusUnauthorized {
				wwwAuth := rec.Header().Get("WWW-Authenticate")
				if wwwAuth == "" {
					t.Error("expected WWW-Authenticate header on 401 response")
				}
			}
		})
	}
}

func TestRequireRole(t *testing.T) {
	adminRoleReq := auth.RequireRole(auth.RoleAdmin)
	operatorRoleReq := auth.RequireRole(auth.RoleAdmin, auth.RoleOperator)
	viewerRoleReq := auth.RequireRole(auth.RoleAdmin, auth.RoleOperator, auth.RoleViewer)

	dummyHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	tests := []struct {
		name           string
		middleware     func(http.Handler) http.Handler
		userRole       auth.Role
		withAuth       bool
		expectedStatus int
	}{
		// Admin endpoint tests
		{
			name:           "admin calling admin endpoint",
			middleware:     adminRoleReq,
			userRole:       auth.RoleAdmin,
			withAuth:       true,
			expectedStatus: http.StatusOK,
		},
		{
			name:           "operator calling admin endpoint",
			middleware:     adminRoleReq,
			userRole:       auth.RoleOperator,
			withAuth:       true,
			expectedStatus: http.StatusForbidden,
		},
		{
			name:           "viewer calling admin endpoint",
			middleware:     adminRoleReq,
			userRole:       auth.RoleViewer,
			withAuth:       true,
			expectedStatus: http.StatusForbidden,
		},
		// Operator endpoint tests
		{
			name:           "admin calling operator endpoint",
			middleware:     operatorRoleReq,
			userRole:       auth.RoleAdmin,
			withAuth:       true,
			expectedStatus: http.StatusOK,
		},
		{
			name:           "operator calling operator endpoint",
			middleware:     operatorRoleReq,
			userRole:       auth.RoleOperator,
			withAuth:       true,
			expectedStatus: http.StatusOK,
		},
		{
			name:           "viewer calling operator endpoint",
			middleware:     operatorRoleReq,
			userRole:       auth.RoleViewer,
			withAuth:       true,
			expectedStatus: http.StatusForbidden,
		},
		// Viewer endpoint tests
		{
			name:           "viewer calling viewer endpoint",
			middleware:     viewerRoleReq,
			userRole:       auth.RoleViewer,
			withAuth:       true,
			expectedStatus: http.StatusOK,
		},
		// Unauthenticated
		{
			name:           "unauthenticated request to role-guarded endpoint",
			middleware:     viewerRoleReq,
			withAuth:       false,
			expectedStatus: http.StatusUnauthorized,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", "/guarded", nil)
			if tt.withAuth {
				claims := &auth.Claims{
					Sub:      "user-x",
					Username: "user",
					Role:     tt.userRole,
				}
				req = req.WithContext(auth.ContextWithClaims(req.Context(), claims))
			}
			rec := httptest.NewRecorder()

			tt.middleware(dummyHandler).ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Fatalf("expected status %d, got %d", tt.expectedStatus, rec.Code)
			}
		})
	}
}
