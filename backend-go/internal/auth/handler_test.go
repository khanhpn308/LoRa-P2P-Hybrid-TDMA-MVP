package auth_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func setupTestHandler(t *testing.T) (*auth.Handler, *auth.Service, auth.UserRepository) {
	t.Helper()
	repo := auth.NewInMemoryUserRepository()
	key := []byte("01234567890123456789012345678901") // 32 bytes
	jwtSvc, err := auth.NewJWTService(key)
	if err != nil {
		t.Fatalf("failed to create jwt service: %v", err)
	}
	ticketStore := auth.NewTicketStore()
	svc := auth.NewService(repo, jwtSvc, ticketStore)
	handler := auth.NewHandler(svc)
	return handler, svc, repo
}

func TestHandler_Login(t *testing.T) {
	handler, _, repo := setupTestHandler(t)
	ctx := context.Background()

	// Seed test user
	hash, err := auth.HashPassword("$StrongP@ss123")
	if err != nil {
		t.Fatalf("failed to hash password: %v", err)
	}
	err = repo.CreateUser(ctx, &auth.User{
		Username:     "testadmin",
		PasswordHash: hash,
		Role:         auth.RoleAdmin,
		IsActive:     true,
	})
	if err != nil {
		t.Fatalf("failed to create user: %v", err)
	}

	// Seed inactive user
	err = repo.CreateUser(ctx, &auth.User{
		Username:     "disabled_user",
		PasswordHash: hash,
		Role:         auth.RoleOperator,
		IsActive:     false,
	})
	if err != nil {
		t.Fatalf("failed to create inactive user: %v", err)
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	tests := []struct {
		name           string
		body           string
		expectedStatus int
		checkResponse  bool
	}{
		{
			name:           "successful login",
			body:           `{"username":"testadmin","password":"$StrongP@ss123"}`,
			expectedStatus: http.StatusOK,
			checkResponse:  true,
		},
		{
			name:           "wrong password",
			body:           `{"username":"testadmin","password":"$WrongPassword123"}`,
			expectedStatus: http.StatusUnauthorized,
			checkResponse:  false,
		},
		{
			name:           "disabled user account",
			body:           `{"username":"disabled_user","password":"$StrongP@ss123"}`,
			expectedStatus: http.StatusUnauthorized,
			checkResponse:  false,
		},
		{
			name:           "nonexistent user",
			body:           `{"username":"ghost","password":"$StrongP@ss123"}`,
			expectedStatus: http.StatusUnauthorized,
			checkResponse:  false,
		},
		{
			name:           "empty username",
			body:           `{"username":"","password":"$StrongP@ss123"}`,
			expectedStatus: http.StatusBadRequest,
			checkResponse:  false,
		},
		{
			name:           "empty password",
			body:           `{"username":"testadmin","password":""}`,
			expectedStatus: http.StatusBadRequest,
			checkResponse:  false,
		},
		{
			name:           "malformed json",
			body:           `{invalid-json}`,
			expectedStatus: http.StatusBadRequest,
			checkResponse:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("POST", "/api/v1/auth/login", bytes.NewBufferString(tt.body))
			req.Header.Set("Content-Type", "application/json")
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Fatalf("expected status %d, got %d (body: %s)", tt.expectedStatus, rec.Code, rec.Body.String())
			}

			if tt.checkResponse {
				var tokenResp auth.TokenResponseDTO
				if err := json.Unmarshal(rec.Body.Bytes(), &tokenResp); err != nil {
					t.Fatalf("failed to decode login response: %v", err)
				}
				if tokenResp.AccessToken == "" {
					t.Error("expected non-empty access_token")
				}
				if tokenResp.TokenType != "Bearer" {
					t.Errorf("expected token_type Bearer, got %q", tokenResp.TokenType)
				}
				if tokenResp.ExpiresIn != 3600 {
					t.Errorf("expected expires_in 3600, got %d", tokenResp.ExpiresIn)
				}
				if tokenResp.Role != auth.RoleAdmin {
					t.Errorf("expected role ADMIN, got %s", tokenResp.Role)
				}
			}
		})
	}
}

func TestHandler_WsTicket(t *testing.T) {
	handler, svc, _ := setupTestHandler(t)

	// Issue valid token for operator
	operatorUser := &auth.User{
		ID:       "user-op-1",
		Username: "operator",
		Role:     auth.RoleOperator,
		IsActive: true,
	}
	validToken, err := svc.JWTService().GenerateToken(operatorUser, 1*time.Hour)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	expiredToken, err := svc.JWTService().GenerateToken(operatorUser, -1*time.Minute)
	if err != nil {
		t.Fatalf("failed to generate expired token: %v", err)
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	tests := []struct {
		name           string
		authHeader     string
		expectedStatus int
		expectTicket   bool
	}{
		{
			name:           "valid bearer token gets ticket",
			authHeader:     "Bearer " + validToken,
			expectedStatus: http.StatusOK,
			expectTicket:   true,
		},
		{
			name:           "missing authorization header",
			authHeader:     "",
			expectedStatus: http.StatusUnauthorized,
			expectTicket:   false,
		},
		{
			name:           "empty bearer token",
			authHeader:     "Bearer ",
			expectedStatus: http.StatusUnauthorized,
			expectTicket:   false,
		},
		{
			name:           "expired bearer token",
			authHeader:     "Bearer " + expiredToken,
			expectedStatus: http.StatusUnauthorized,
			expectTicket:   false,
		},
		{
			name:           "invalid bearer token signature",
			authHeader:     "Bearer " + validToken + "invalid",
			expectedStatus: http.StatusUnauthorized,
			expectTicket:   false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("POST", "/api/v1/auth/ws-ticket", nil)
			if tt.authHeader != "" {
				req.Header.Set("Authorization", tt.authHeader)
			}
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Fatalf("expected status %d, got %d (body: %s)", tt.expectedStatus, rec.Code, rec.Body.String())
			}

			if tt.expectTicket {
				var ticketResp auth.WsTicketResponseDTO
				if err := json.Unmarshal(rec.Body.Bytes(), &ticketResp); err != nil {
					t.Fatalf("failed to decode ws-ticket response: %v", err)
				}
				if ticketResp.Ticket == "" {
					t.Error("expected non-empty ticket")
				}
				if ticketResp.ExpiresIn != 30 {
					t.Errorf("expected expires_in 30, got %d", ticketResp.ExpiresIn)
				}

				// Consume ticket through service
				claims, ok := svc.ConsumeWsTicket(ticketResp.Ticket)
				if !ok || claims == nil {
					t.Fatal("first consumption of issued ticket must succeed")
				}
				if claims.Role != auth.RoleOperator {
					t.Errorf("expected role OPERATOR, got %s", claims.Role)
				}

				// Second consumption must fail
				secondClaims, secondOk := svc.ConsumeWsTicket(ticketResp.Ticket)
				if secondOk || secondClaims != nil {
					t.Fatal("second consumption of issued ticket must fail (replay protection)")
				}
			}
		})
	}
}

func TestHandler_ListUsers(t *testing.T) {
	handler, svc, repo := setupTestHandler(t)
	ctx := context.Background()

	_ = repo.CreateUser(ctx, &auth.User{
		Username: "admin_tester",
		Role:     auth.RoleAdmin,
		IsActive: true,
	})

	validToken, err := svc.JWTService().GenerateToken(&auth.User{
		ID:       "u-admin",
		Username: "admin_tester",
		Role:     auth.RoleAdmin,
		IsActive: true,
	}, time.Hour)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// Test authenticated request
	req := httptest.NewRequest(http.MethodGet, "/api/v1/users", nil)
	req.Header.Set("Authorization", "Bearer "+validToken)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var users []*auth.User
	if err := json.Unmarshal(rec.Body.Bytes(), &users); err != nil {
		t.Fatalf("failed to decode users response: %v", err)
	}
	if len(users) != 1 || users[0].Username != "admin_tester" {
		t.Fatalf("unexpected users returned: %+v", users)
	}

	// Test unauthenticated request
	unauthReq := httptest.NewRequest(http.MethodGet, "/api/v1/users", nil)
	unauthRec := httptest.NewRecorder()
	mux.ServeHTTP(unauthRec, unauthReq)

	if unauthRec.Code != http.StatusUnauthorized {
		t.Fatalf("expected status 401 for unauthenticated request, got %d", unauthRec.Code)
	}
}

func TestHandler_CreateUser(t *testing.T) {
	handler, svc, repo := setupTestHandler(t)
	ctx := context.Background()

	_ = repo.CreateUser(ctx, &auth.User{
		Username: "admin_tester",
		Role:     auth.RoleAdmin,
		IsActive: true,
	})

	adminToken, err := svc.JWTService().GenerateToken(&auth.User{
		ID:       "u-admin",
		Username: "admin_tester",
		Role:     auth.RoleAdmin,
		IsActive: true,
	}, time.Hour)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	viewerToken, err := svc.JWTService().GenerateToken(&auth.User{
		ID:       "u-viewer",
		Username: "viewer_tester",
		Role:     auth.RoleViewer,
		IsActive: true,
	}, time.Hour)
	if err != nil {
		t.Fatalf("failed to generate viewer token: %v", err)
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// 1. Success creating user by ADMIN
	payload := `{"username":"newoperator","full_name":"Nguyen Van New","email":"new@lora.vn","password":"validPassword123","role":"OPERATOR"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/users", strings.NewReader(payload))
	req.Header.Set("Authorization", "Bearer "+adminToken)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d: %s", rec.Code, rec.Body.String())
	}

	var created auth.User
	if err := json.Unmarshal(rec.Body.Bytes(), &created); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if created.Username != "newoperator" || created.FullName != "Nguyen Van New" || created.Email != "new@lora.vn" || created.Role != auth.RoleOperator {
		t.Fatalf("unexpected created user: %+v", created)
	}

	// 2. Duplicate user should return 409 Conflict
	dupReq := httptest.NewRequest(http.MethodPost, "/api/v1/users", strings.NewReader(payload))
	dupReq.Header.Set("Authorization", "Bearer "+adminToken)
	dupRec := httptest.NewRecorder()
	mux.ServeHTTP(dupRec, dupReq)

	if dupRec.Code != http.StatusConflict {
		t.Fatalf("expected status 409 for duplicate user, got %d", dupRec.Code)
	}

	// 3. Short password should return 400 Bad Request
	shortPwPayload := `{"username":"user3","password":"123","role":"OPERATOR"}`
	shortReq := httptest.NewRequest(http.MethodPost, "/api/v1/users", strings.NewReader(shortPwPayload))
	shortReq.Header.Set("Authorization", "Bearer "+adminToken)
	shortRec := httptest.NewRecorder()
	mux.ServeHTTP(shortRec, shortReq)

	if shortRec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400 for short password, got %d", shortRec.Code)
	}

	// 4. Non-admin caller should return 403 Forbidden
	nonAdminReq := httptest.NewRequest(http.MethodPost, "/api/v1/users", strings.NewReader(`{"username":"user4","password":"validPassword123"}`))
	nonAdminReq.Header.Set("Authorization", "Bearer "+viewerToken)
	nonAdminRec := httptest.NewRecorder()
	mux.ServeHTTP(nonAdminRec, nonAdminReq)

	if nonAdminRec.Code != http.StatusForbidden {
		t.Fatalf("expected status 403 for non-admin user, got %d", nonAdminRec.Code)
	}
}

func TestHandler_GetUser(t *testing.T) {
	handler, svc, repo := setupTestHandler(t)
	ctx := context.Background()

	_ = repo.CreateUser(ctx, &auth.User{
		ID:       "uuid-001",
		Username: "operator_bob",
		FullName: "Bob Operator",
		Email:    "bob@iiot.vn",
		Role:     auth.RoleOperator,
		IsActive: true,
	})

	validToken, _ := svc.JWTService().GenerateToken(&auth.User{
		ID:       "uuid-admin",
		Username: "admin_tester",
		Role:     auth.RoleAdmin,
		IsActive: true,
	}, time.Hour)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// 1. Get by username
	req := httptest.NewRequest(http.MethodGet, "/api/v1/users/operator_bob", nil)
	req.Header.Set("Authorization", "Bearer "+validToken)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var u auth.User
	_ = json.Unmarshal(rec.Body.Bytes(), &u)
	if u.Username != "operator_bob" || u.FullName != "Bob Operator" {
		t.Fatalf("unexpected user: %+v", u)
	}

	// 2. Get non-existent
	notFoundReq := httptest.NewRequest(http.MethodGet, "/api/v1/users/nonexistent", nil)
	notFoundReq.Header.Set("Authorization", "Bearer "+validToken)
	notFoundRec := httptest.NewRecorder()
	mux.ServeHTTP(notFoundRec, notFoundReq)

	if notFoundRec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", notFoundRec.Code)
	}
}

func TestHandler_UpdateUser(t *testing.T) {
	handler, svc, repo := setupTestHandler(t)
	ctx := context.Background()

	hash, _ := auth.HashPassword("$Password12345")
	_ = repo.CreateUser(ctx, &auth.User{
		ID:           "uuid-alice",
		Username:     "alice",
		FullName:     "Alice Smith",
		Email:        "alice@example.com",
		PasswordHash: hash,
		Role:         auth.RoleViewer,
		IsActive:     true,
	})

	adminToken, _ := svc.JWTService().GenerateToken(&auth.User{
		ID:       "uuid-admin",
		Username: "admin_user",
		Role:     auth.RoleAdmin,
		IsActive: true,
	}, time.Hour)

	operatorToken, _ := svc.JWTService().GenerateToken(&auth.User{
		ID:       "uuid-operator",
		Username: "operator_user",
		Role:     auth.RoleOperator,
		IsActive: true,
	}, time.Hour)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// 1. Admin updates Alice's full name, email, and role
	body := `{"full_name":"Alice Jones","email":"alice.jones@example.com","role":"OPERATOR"}`
	req := httptest.NewRequest(http.MethodPatch, "/api/v1/users/uuid-alice", bytes.NewBufferString(body))
	req.Header.Set("Authorization", "Bearer "+adminToken)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var updated auth.User
	_ = json.Unmarshal(rec.Body.Bytes(), &updated)
	if updated.FullName != "Alice Jones" || updated.Email != "alice.jones@example.com" || updated.Role != auth.RoleOperator {
		t.Fatalf("unexpected user state: %+v", updated)
	}

	// 2. Admin deactivates Alice
	deactivateBody := `{"is_active":false}`
	deactivateReq := httptest.NewRequest(http.MethodPatch, "/api/v1/users/alice", bytes.NewBufferString(deactivateBody))
	deactivateReq.Header.Set("Authorization", "Bearer "+adminToken)
	deactivateReq.Header.Set("Content-Type", "application/json")
	deactivateRec := httptest.NewRecorder()
	mux.ServeHTTP(deactivateRec, deactivateReq)

	if deactivateRec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", deactivateRec.Code, deactivateRec.Body.String())
	}

	// 3. Deactivated user cannot log in
	loginBody := `{"username":"alice","password":"$Password12345"}`
	loginReq := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", bytes.NewBufferString(loginBody))
	loginReq.Header.Set("Content-Type", "application/json")
	loginRec := httptest.NewRecorder()
	mux.ServeHTTP(loginRec, loginReq)

	if loginRec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for inactive account, got %d: %s", loginRec.Code, loginRec.Body.String())
	}
	if !strings.Contains(loginRec.Body.String(), "inactive") {
		t.Fatalf("expected message mentioning inactive, got: %s", loginRec.Body.String())
	}

	// 4. Admin reactivates Alice
	reactivateBody := `{"is_active":true}`
	reactivateReq := httptest.NewRequest(http.MethodPatch, "/api/v1/users/alice", bytes.NewBufferString(reactivateBody))
	reactivateReq.Header.Set("Authorization", "Bearer "+adminToken)
	reactivateReq.Header.Set("Content-Type", "application/json")
	reactivateRec := httptest.NewRecorder()
	mux.ServeHTTP(reactivateRec, reactivateReq)

	if reactivateRec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", reactivateRec.Code)
	}

	// 5. Reactivated user can log in again
	loginReq2 := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", bytes.NewBufferString(loginBody))
	loginReq2.Header.Set("Content-Type", "application/json")
	loginRec2 := httptest.NewRecorder()
	mux.ServeHTTP(loginRec2, loginReq2)

	if loginRec2.Code != http.StatusOK {
		t.Fatalf("expected 200 for reactivated account, got %d: %s", loginRec2.Code, loginRec2.Body.String())
	}

	// 6. Non-admin operator cannot update users (403 Forbidden)
	opReq := httptest.NewRequest(http.MethodPatch, "/api/v1/users/alice", bytes.NewBufferString(body))
	opReq.Header.Set("Authorization", "Bearer "+operatorToken)
	opReq.Header.Set("Content-Type", "application/json")
	opRec := httptest.NewRecorder()
	mux.ServeHTTP(opRec, opReq)

	if opRec.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-admin, got %d", opRec.Code)
	}

	// 7. Unauthenticated request (401 Unauthorized)
	unauthReq := httptest.NewRequest(http.MethodPatch, "/api/v1/users/alice", bytes.NewBufferString(body))
	unauthRec := httptest.NewRecorder()
	mux.ServeHTTP(unauthRec, unauthReq)

	if unauthRec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for unauthenticated request, got %d", unauthRec.Code)
	}

	// 8. Invalid role (400 Bad Request)
	invalidRoleBody := `{"role":"SUPERUSER"}`
	badRoleReq := httptest.NewRequest(http.MethodPatch, "/api/v1/users/alice", bytes.NewBufferString(invalidRoleBody))
	badRoleReq.Header.Set("Authorization", "Bearer "+adminToken)
	badRoleReq.Header.Set("Content-Type", "application/json")
	badRoleRec := httptest.NewRecorder()
	mux.ServeHTTP(badRoleRec, badRoleReq)

	if badRoleRec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid role, got %d", badRoleRec.Code)
	}
}

func TestHandler_UpdatePassword(t *testing.T) {
	handler, svc, repo := setupTestHandler(t)
	ctx := context.Background()

	oldPass := "$OldSecret123"
	hash, _ := auth.HashPassword(oldPass)
	_ = repo.CreateUser(ctx, &auth.User{
		ID:           "uuid-bob",
		Username:     "bob",
		FullName:     "Bob Operator",
		Email:        "bob@example.com",
		PasswordHash: hash,
		Role:         auth.RoleOperator,
		IsActive:     true,
	})

	adminToken, _ := svc.JWTService().GenerateToken(&auth.User{
		ID:       "uuid-admin",
		Username: "admin_user",
		Role:     auth.RoleAdmin,
		IsActive: true,
	}, time.Hour)

	bobToken, _ := svc.JWTService().GenerateToken(&auth.User{
		ID:       "uuid-bob",
		Username: "bob",
		Role:     auth.RoleOperator,
		IsActive: true,
	}, time.Hour)

	charlieToken, _ := svc.JWTService().GenerateToken(&auth.User{
		ID:       "uuid-charlie",
		Username: "charlie",
		Role:     auth.RoleOperator,
		IsActive: true,
	}, time.Hour)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// 1. Bob resets his own password
	newBobPass := "$NewBobSecret456"
	selfReq := httptest.NewRequest(http.MethodPut, "/api/v1/users/bob/password", bytes.NewBufferString(`{"password":"`+newBobPass+`"}`))
	selfReq.Header.Set("Authorization", "Bearer "+bobToken)
	selfReq.Header.Set("Content-Type", "application/json")
	selfRec := httptest.NewRecorder()
	mux.ServeHTTP(selfRec, selfReq)

	if selfRec.Code != http.StatusOK {
		t.Fatalf("expected 200 for self password reset, got %d: %s", selfRec.Code, selfRec.Body.String())
	}

	// Bob logs in with new password
	loginReq := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", bytes.NewBufferString(`{"username":"bob","password":"`+newBobPass+`"}`))
	loginReq.Header.Set("Content-Type", "application/json")
	loginRec := httptest.NewRecorder()
	mux.ServeHTTP(loginRec, loginReq)

	if loginRec.Code != http.StatusOK {
		t.Fatalf("expected 200 for login with new password, got %d: %s", loginRec.Code, loginRec.Body.String())
	}

	// 2. Admin resets Bob's password
	adminResetPass := "$AdminResetSecret789"
	adminReq := httptest.NewRequest(http.MethodPut, "/api/v1/users/uuid-bob/password", bytes.NewBufferString(`{"password":"`+adminResetPass+`"}`))
	adminReq.Header.Set("Authorization", "Bearer "+adminToken)
	adminReq.Header.Set("Content-Type", "application/json")
	adminRec := httptest.NewRecorder()
	mux.ServeHTTP(adminRec, adminReq)

	if adminRec.Code != http.StatusOK {
		t.Fatalf("expected 200 for admin password reset, got %d: %s", adminRec.Code, adminRec.Body.String())
	}

	// 3. Charlie (operator) tries to reset Bob's password -> 403 Forbidden
	charlieReq := httptest.NewRequest(http.MethodPut, "/api/v1/users/bob/password", bytes.NewBufferString(`{"password":"$HackedPassword123"}`))
	charlieReq.Header.Set("Authorization", "Bearer "+charlieToken)
	charlieReq.Header.Set("Content-Type", "application/json")
	charlieRec := httptest.NewRecorder()
	mux.ServeHTTP(charlieRec, charlieReq)

	if charlieRec.Code != http.StatusForbidden {
		t.Fatalf("expected 403 when non-admin resets another user's password, got %d", charlieRec.Code)
	}

	// 4. Password too short (<8 chars) -> 400 Bad Request
	shortReq := httptest.NewRequest(http.MethodPut, "/api/v1/users/bob/password", bytes.NewBufferString(`{"password":"short"}`))
	shortReq.Header.Set("Authorization", "Bearer "+adminToken)
	shortReq.Header.Set("Content-Type", "application/json")
	shortRec := httptest.NewRecorder()
	mux.ServeHTTP(shortRec, shortReq)

	if shortRec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for short password, got %d", shortRec.Code)
	}
}
