package api_test

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockProvisionRepo struct {
	provisionFunc func(ctx context.Context, input *storage.ProvisionDeviceInput) (*storage.ProvisionDeviceResult, error)
}

func (m *mockProvisionRepo) ProvisionDevice(ctx context.Context, input *storage.ProvisionDeviceInput) (*storage.ProvisionDeviceResult, error) {
	if m.provisionFunc != nil {
		return m.provisionFunc(ctx, input)
	}
	return &storage.ProvisionDeviceResult{
		NetworkID:  input.NetworkID,
		DeviceMAC:  input.DeviceMAC,
		Generation: input.Generation,
		Status:     "ACTIVE",
		CreatedAt:  time.Date(2026, 11, 8, 0, 0, 0, 0, time.UTC),
	}, nil
}

func testMasterKey() [32]byte {
	var k [32]byte
	for i := range k {
		k[i] = byte(i + 1)
	}
	return k
}

func TestProvisionHandler_Table(t *testing.T) {
	masterKey := testMasterKey()
	keyWrapper := security.NewAESGCMKeyWrapper(masterKey)

	authenticator := api.NewStaticAuthenticator(map[string]api.Role{
		"admin-token":    api.RoleAdmin,
		"operator-token": api.RoleOperator,
		"viewer-token":   api.RoleViewer,
	})

	validHexKey := "0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20"
	rawKeyBytes, _ := hex.DecodeString(validHexKey)
	validB64Key := base64.StdEncoding.EncodeToString(rawKeyBytes)

	tests := []struct {
		name           string
		authHeader     string
		body           string
		mockRepo       *mockProvisionRepo
		expectedStatus int
		expectInBody   []string
		forbidInBody   []string
	}{
		{
			name:           "positive registration with hex key (HTTP 201)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusCreated,
			expectInBody: []string{
				`"device_mac":"001122334455"`,
				`"network_id":1`,
				`"generation":1`,
				`"status":"ACTIVE"`,
				`"created_at":`,
			},
			forbidInBody: []string{
				validHexKey,
				validB64Key,
				"k_join",
			},
		},
		{
			name:           "positive registration with base64 key (HTTP 201)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "aabbccddeeff", "k_join": "` + validB64Key + `", "generation": 2, "initial_join_counter": 5}`,
			expectedStatus: http.StatusCreated,
			expectInBody: []string{
				`"device_mac":"aabbccddeeff"`,
				`"network_id":1`,
				`"generation":2`,
				`"status":"ACTIVE"`,
			},
			forbidInBody: []string{
				validHexKey,
				validB64Key,
				"k_join",
			},
		},
		{
			name:           "missing authorization header (HTTP 401)",
			authHeader:     "",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusUnauthorized,
			expectInBody:   []string{`"error":"UNAUTHORIZED"`},
		},
		{
			name:           "invalid bearer token (HTTP 401)",
			authHeader:     "Bearer invalid-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusUnauthorized,
			expectInBody:   []string{`"error":"UNAUTHORIZED"`},
		},
		{
			name:           "non-admin operator token (HTTP 403)",
			authHeader:     "Bearer operator-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusForbidden,
			expectInBody:   []string{`"error":"FORBIDDEN"`},
		},
		{
			name:           "non-admin viewer token (HTTP 403)",
			authHeader:     "Bearer viewer-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusForbidden,
			expectInBody:   []string{`"error":"FORBIDDEN"`},
		},
		{
			name:           "malformed MAC - uppercase not canonical (HTTP 400)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "0011223344FF", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"INVALID_DEVICE_MAC"`},
		},
		{
			name:           "malformed MAC - too short (HTTP 400)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "0011223344", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"INVALID_DEVICE_MAC"`},
		},
		{
			name:           "malformed MAC - invalid characters (HTTP 400)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "0011223344zz", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"INVALID_DEVICE_MAC"`},
		},
		{
			name:           "truncated key size - 16 bytes hex (HTTP 400)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "0102030405060708090a0b0c0d0e0f10"}`,
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"INVALID_K_JOIN"`},
		},
		{
			name:           "extended key size - 40 bytes hex (HTTP 400)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `0102030405060708` + `"}`,
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"INVALID_K_JOIN"`},
		},
		{
			name:           "zero network_id (HTTP 400)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 0, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"INVALID_NETWORK_ID"`},
		},
		{
			name:           "invalid generation zero (HTTP 400)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `", "generation": 0}`,
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"INVALID_GENERATION"`},
		},
		{
			name:           "malformed JSON body (HTTP 400)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", `,
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"MALFORMED_JSON"`},
		},
		{
			name:           "empty bearer token string (HTTP 401)",
			authHeader:     "Bearer   ",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			expectedStatus: http.StatusUnauthorized,
			expectInBody:   []string{`"error":"UNAUTHORIZED"`},
		},
		{
			name:           "empty k_join string (HTTP 400)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": ""}`,
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"INVALID_K_JOIN"`},
		},
		{
			name:           "unpadded base64 key (HTTP 201)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + base64.RawStdEncoding.EncodeToString(rawKeyBytes) + `"}`,
			expectedStatus: http.StatusCreated,
			expectInBody:   []string{`"status":"ACTIVE"`},
		},
		{
			name:           "url-safe base64 key (HTTP 201)",
			authHeader:     "Bearer admin-token",
			body:           `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + base64.URLEncoding.EncodeToString(rawKeyBytes) + `"}`,
			expectedStatus: http.StatusCreated,
			expectInBody:   []string{`"status":"ACTIVE"`},
		},
		{
			name:       "storage invalid provision input maps to 400 (HTTP 400)",
			authHeader: "Bearer admin-token",
			body:       `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			mockRepo: &mockProvisionRepo{
				provisionFunc: func(ctx context.Context, input *storage.ProvisionDeviceInput) (*storage.ProvisionDeviceResult, error) {
					return nil, storage.ErrInvalidProvisionInput
				},
			},
			expectedStatus: http.StatusBadRequest,
			expectInBody:   []string{`"error":"INVALID_INPUT"`},
		},
		{
			name:       "conflict on existing active generation (HTTP 409)",
			authHeader: "Bearer admin-token",
			body:       `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			mockRepo: &mockProvisionRepo{
				provisionFunc: func(ctx context.Context, input *storage.ProvisionDeviceInput) (*storage.ProvisionDeviceResult, error) {
					return nil, storage.ErrDeviceAlreadyProvisioned
				},
			},
			expectedStatus: http.StatusConflict,
			expectInBody:   []string{`"error":"CONFLICT"`},
		},
		{
			name:       "conflict on duplicate generation number (HTTP 409)",
			authHeader: "Bearer admin-token",
			body:       `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `", "generation": 1}`,
			mockRepo: &mockProvisionRepo{
				provisionFunc: func(ctx context.Context, input *storage.ProvisionDeviceInput) (*storage.ProvisionDeviceResult, error) {
					return nil, storage.ErrGenerationAlreadyExists
				},
			},
			expectedStatus: http.StatusConflict,
			expectInBody:   []string{`"error":"CONFLICT"`},
		},
		{
			name:       "device not active conflict (HTTP 409)",
			authHeader: "Bearer admin-token",
			body:       `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			mockRepo: &mockProvisionRepo{
				provisionFunc: func(ctx context.Context, input *storage.ProvisionDeviceInput) (*storage.ProvisionDeviceResult, error) {
					return nil, storage.ErrDeviceNotActive
				},
			},
			expectedStatus: http.StatusConflict,
			expectInBody:   []string{`"error":"DEVICE_NOT_ACTIVE"`},
		},
		{
			name:       "internal storage error (HTTP 500)",
			authHeader: "Bearer admin-token",
			body:       `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`,
			mockRepo: &mockProvisionRepo{
				provisionFunc: func(ctx context.Context, input *storage.ProvisionDeviceInput) (*storage.ProvisionDeviceResult, error) {
					return nil, errors.New("database connection refused")
				},
			},
			expectedStatus: http.StatusInternalServerError,
			expectInBody:   []string{`"error":"INTERNAL_ERROR"`},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			repo := tt.mockRepo
			if repo == nil {
				repo = &mockProvisionRepo{}
			}

			handler := api.NewProvisionHandler(repo, keyWrapper, authenticator)
			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)

			req := httptest.NewRequest(http.MethodPost, "/api/v1/devices/provision", bytes.NewBufferString(tt.body))
			req.Header.Set("Content-Type", "application/json")
			if tt.authHeader != "" {
				req.Header.Set("Authorization", tt.authHeader)
			}

			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Fatalf("status code mismatch: got %d, want %d. Body: %s", rec.Code, tt.expectedStatus, rec.Body.String())
			}

			bodyStr := rec.Body.String()
			for _, exp := range tt.expectInBody {
				if !strings.Contains(bodyStr, exp) {
					t.Errorf("expected %q in response body, got: %s", exp, bodyStr)
				}
			}
			for _, forbid := range tt.forbidInBody {
				if strings.Contains(bodyStr, forbid) {
					t.Errorf("forbidden string %q detected in response body: %s", forbid, bodyStr)
				}
			}
		})
	}
}

type errKeyWrapper struct{}

func (e *errKeyWrapper) Wrap(plaintext []byte) ([]byte, error) {
	return nil, errors.New("wrap failure")
}

func TestProvisionHandler_WrapFailure(t *testing.T) {
	repo := &mockProvisionRepo{}
	auth := api.NewStaticAuthenticator(map[string]api.Role{"admin-token": api.RoleAdmin})
	handler := api.NewProvisionHandler(repo, &errKeyWrapper{}, auth)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	validHexKey := "0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20"
	body := `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`

	req := httptest.NewRequest(http.MethodPost, "/api/v1/devices/provision", bytes.NewBufferString(body))
	req.Header.Set("Authorization", "Bearer admin-token")
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Errorf("expected 500 on wrap failure, got %d", rec.Code)
	}
}

func TestProvisionHandler_UnconfiguredDependencies(t *testing.T) {
	repo := &mockProvisionRepo{}
	masterKey := testMasterKey()
	wrapper := security.NewAESGCMKeyWrapper(masterKey)

	// Nil authenticator
	h1 := api.NewProvisionHandler(repo, wrapper, nil)
	mux1 := http.NewServeMux()
	h1.RegisterRoutes(mux1)

	validHexKey := "0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20"
	body := `{"network_id": 1, "device_mac": "001122334455", "k_join": "` + validHexKey + `"}`

	req1 := httptest.NewRequest(http.MethodPost, "/api/v1/devices/provision", bytes.NewBufferString(body))
	req1.Header.Set("Authorization", "Bearer some-token")
	rec1 := httptest.NewRecorder()
	mux1.ServeHTTP(rec1, req1)
	if rec1.Code != http.StatusInternalServerError {
		t.Errorf("expected 500 for unconfigured authenticator, got %d", rec1.Code)
	}

	// Nil keyWrapper
	auth := api.NewStaticAuthenticator(map[string]api.Role{"admin-token": api.RoleAdmin})
	h2 := api.NewProvisionHandler(repo, nil, auth)
	mux2 := http.NewServeMux()
	h2.RegisterRoutes(mux2)

	req2 := httptest.NewRequest(http.MethodPost, "/api/v1/devices/provision", bytes.NewBufferString(body))
	req2.Header.Set("Authorization", "Bearer admin-token")
	rec2 := httptest.NewRecorder()
	mux2.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusInternalServerError {
		t.Errorf("expected 500 for unconfigured keyWrapper, got %d", rec2.Code)
	}
}
