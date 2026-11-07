package api_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockAlertRepo struct {
	alerts       []domain.AlertView
	acknowledged map[int64]bool
}

func newMockAlertRepo() *mockAlertRepo {
	now := time.Date(2026, 11, 8, 1, 0, 0, 0, time.UTC).Format(time.RFC3339)
	return &mockAlertRepo{
		acknowledged: make(map[int64]bool),
		alerts: []domain.AlertView{
			{
				AlertID:    "102",
				NodeID:     2,
				GatewayID:  "gw01",
				EventRef:   2,
				EventCode:  1,
				EventValue: 1,
				Severity:   domain.SeverityP0Emergency,
				ReceivedAt: now,
				AckStatus:  domain.AckStatusUnacknowledged,
			},
			{
				AlertID:    "101",
				NodeID:     1,
				GatewayID:  "gw01",
				EventRef:   1,
				EventCode:  1,
				EventValue: 1,
				Severity:   domain.SeverityP1High,
				ReceivedAt: now,
				AckStatus:  domain.AckStatusUnacknowledged,
			},
		},
	}
}

func (m *mockAlertRepo) ListAlerts(ctx context.Context, filter domain.AlertFilter) (*domain.AlertPage, error) {
	var filtered []domain.AlertView
	for _, a := range m.alerts {
		if filter.Severity != "" && string(a.Severity) != filter.Severity {
			continue
		}
		if filter.NodeID != nil && a.NodeID != *filter.NodeID {
			continue
		}
		if filter.GatewayID != "" && a.GatewayID != filter.GatewayID {
			continue
		}
		if filter.AckStatus != "" && string(a.AckStatus) != filter.AckStatus {
			continue
		}
		filtered = append(filtered, a)
	}

	limit := filter.Limit
	if limit <= 0 {
		limit = 50
	}
	var nextCursor *string
	if len(filtered) > limit {
		filtered = filtered[:limit]
		c := filtered[len(filtered)-1].AlertID
		nextCursor = &c
	}
	return &domain.AlertPage{
		Items:      filtered,
		NextCursor: nextCursor,
	}, nil
}

func (m *mockAlertRepo) AcknowledgeAlert(ctx context.Context, alertID int64, acknowledgedBy string) (*domain.AlertView, error) {
	if alertID == 999 {
		return nil, storage.ErrAlertNotFound
	}
	for i := range m.alerts {
		a := &m.alerts[i]
		if a.AlertID == strconv.FormatInt(alertID, 10) {
			m.acknowledged[alertID] = true
			now := time.Now().UTC().Format(time.RFC3339)
			a.AckStatus = domain.AckStatusAcknowledged
			a.AckedAt = &now
			return a, nil
		}
	}
	return nil, storage.ErrAlertNotFound
}

func setupAlertRouter(repo api.AlertRepository, auth ...api.Authenticator) http.Handler {
	handler := api.NewAlertHandler(repo, auth...)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	return mux
}

func TestAlertHandler_ListAlerts_Table(t *testing.T) {
	repo := newMockAlertRepo()
	router := setupAlertRouter(repo)

	tests := []struct {
		name       string
		query      string
		wantCode   int
		wantItems  int
		wantCursor bool
	}{
		{
			name:       "positive default first page",
			query:      "",
			wantCode:   http.StatusOK,
			wantItems:  2,
			wantCursor: false,
		},
		{
			name:       "positive with limit 10",
			query:      "?limit=10",
			wantCode:   http.StatusOK,
			wantItems:  2,
			wantCursor: false,
		},
		{
			name:       "positive filtered by severity",
			query:      "?severity=P0_EMERGENCY",
			wantCode:   http.StatusOK,
			wantItems:  1,
			wantCursor: false,
		},
		{
			name:       "positive filtered by node_id",
			query:      "?node_id=2",
			wantCode:   http.StatusOK,
			wantItems:  1,
			wantCursor: false,
		},
		{
			name:       "positive filtered by gateway_id",
			query:      "?gateway_id=gw01",
			wantCode:   http.StatusOK,
			wantItems:  2,
			wantCursor: false,
		},
		{
			name:       "positive filtered by ack_status",
			query:      "?ack_status=UNACKNOWLEDGED",
			wantCode:   http.StatusOK,
			wantItems:  2,
			wantCursor: false,
		},
		{
			name:       "pagination with cursor and limit=1",
			query:      "?cursor=105&limit=1",
			wantCode:   http.StatusOK,
			wantItems:  1,
			wantCursor: true,
		},
		{
			name:     "invalid negative limit",
			query:    "?limit=-5",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid zero limit",
			query:    "?limit=0",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid excessive limit",
			query:    "?limit=101",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid non-numeric limit",
			query:    "?limit=abc",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid negative cursor",
			query:    "?cursor=-10",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid non-numeric cursor",
			query:    "?cursor=invalid",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid severity enum",
			query:    "?severity=CRITICAL",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid node_id zero",
			query:    "?node_id=0",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid node_id 255",
			query:    "?node_id=255",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid gateway_id with special characters",
			query:    "?gateway_id=gw!@#$",
			wantCode: http.StatusUnprocessableEntity,
		},
		{
			name:     "invalid ack_status enum",
			query:    "?ack_status=UNKNOWN",
			wantCode: http.StatusUnprocessableEntity,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", "/api/v1/alerts"+tc.query, nil)
			rec := httptest.NewRecorder()

			router.ServeHTTP(rec, req)

			if rec.Code != tc.wantCode {
				t.Fatalf("expected status %d, got %d (body: %s)", tc.wantCode, rec.Code, rec.Body.String())
			}
			if tc.wantCode == http.StatusOK {
				var page domain.AlertPage
				if err := json.Unmarshal(rec.Body.Bytes(), &page); err != nil {
					t.Fatalf("failed to decode AlertPage: %v", err)
				}
				if len(page.Items) != tc.wantItems {
					t.Errorf("expected %d items, got %d", tc.wantItems, len(page.Items))
				}
				if (page.NextCursor != nil) != tc.wantCursor {
					t.Errorf("expected NextCursor != nil to be %v, got %v", tc.wantCursor, page.NextCursor)
				}
			}
		})
	}
}

func TestAlertHandler_AcknowledgeAlert_Table(t *testing.T) {
	tests := []struct {
		name       string
		alertID    string
		body       string
		wantCode   int
		wantStatus domain.AckStatus
	}{
		{
			name:       "positive initial acknowledgment",
			alertID:    "101",
			body:       `{"acknowledged_by":"ops_lead"}`,
			wantCode:   http.StatusOK,
			wantStatus: domain.AckStatusAcknowledged,
		},
		{
			name:       "idempotent re-acknowledgment on already acknowledged alert",
			alertID:    "101",
			body:       "",
			wantCode:   http.StatusOK,
			wantStatus: domain.AckStatusAcknowledged,
		},
		{
			name:     "alert not found returns 404",
			alertID:  "999",
			body:     "",
			wantCode: http.StatusNotFound,
		},
		{
			name:     "malformed alert_id alphabetic",
			alertID:  "invalid_id",
			body:     "",
			wantCode: http.StatusBadRequest,
		},
		{
			name:     "malformed alert_id with leading zero",
			alertID:  "0123",
			body:     "",
			wantCode: http.StatusBadRequest,
		},
		{
			name:     "malformed alert_id negative",
			alertID:  "-1",
			body:     "",
			wantCode: http.StatusBadRequest,
		},
		{
			name:     "malformed JSON body returns 400",
			alertID:  "102",
			body:     `{"acknowledged_by": invalid_json}`,
			wantCode: http.StatusBadRequest,
		},
	}

	repo := newMockAlertRepo()
	router := setupAlertRouter(repo)

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			var bodyReader = strings.NewReader(tc.body)
			req := httptest.NewRequest("POST", "/api/v1/alerts/"+tc.alertID+"/acknowledge", bodyReader)
			if tc.body != "" {
				req.Header.Set("Content-Type", "application/json")
			}
			rec := httptest.NewRecorder()

			router.ServeHTTP(rec, req)

			if rec.Code != tc.wantCode {
				t.Fatalf("expected status %d, got %d (body: %s)", tc.wantCode, rec.Code, rec.Body.String())
			}
			if tc.wantCode == http.StatusOK {
				var view domain.AlertView
				if err := json.Unmarshal(rec.Body.Bytes(), &view); err != nil {
					t.Fatalf("failed to decode AlertView: %v", err)
				}
				if view.AckStatus != tc.wantStatus {
					t.Errorf("expected AckStatus %s, got %s", tc.wantStatus, view.AckStatus)
				}
				if view.AckedAt == nil {
					t.Errorf("expected AckedAt to be populated")
				}
			}
		})
	}
}

func TestAlertHandler_RBAC_Table(t *testing.T) {
	auth := api.NewStaticAuthenticator(map[string]api.Role{
		"viewer-tok":   api.RoleViewer,
		"operator-tok": api.RoleOperator,
		"admin-tok":    api.RoleAdmin,
	})

	repo := newMockAlertRepo()
	router := setupAlertRouter(repo, auth)

	tests := []struct {
		name       string
		method     string
		path       string
		authHeader string
		wantCode   int
	}{
		{
			name:       "GET /alerts missing token -> 401",
			method:     "GET",
			path:       "/api/v1/alerts",
			authHeader: "",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "GET /alerts invalid token -> 401",
			method:     "GET",
			path:       "/api/v1/alerts",
			authHeader: "Bearer bad-token",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "GET /alerts VIEWER token -> 200",
			method:     "GET",
			path:       "/api/v1/alerts",
			authHeader: "Bearer viewer-tok",
			wantCode:   http.StatusOK,
		},
		{
			name:       "GET /alerts OPERATOR token -> 200",
			method:     "GET",
			path:       "/api/v1/alerts",
			authHeader: "Bearer operator-tok",
			wantCode:   http.StatusOK,
		},
		{
			name:       "GET /alerts ADMIN token -> 200",
			method:     "GET",
			path:       "/api/v1/alerts",
			authHeader: "Bearer admin-tok",
			wantCode:   http.StatusOK,
		},
		{
			name:       "POST /alerts/{id}/ack missing token -> 401",
			method:     "POST",
			path:       "/api/v1/alerts/101/acknowledge",
			authHeader: "",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "POST /alerts/{id}/ack invalid token -> 401",
			method:     "POST",
			path:       "/api/v1/alerts/101/acknowledge",
			authHeader: "Bearer bad-token",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "POST /alerts/{id}/ack VIEWER token -> 403 Forbidden",
			method:     "POST",
			path:       "/api/v1/alerts/101/acknowledge",
			authHeader: "Bearer viewer-tok",
			wantCode:   http.StatusForbidden,
		},
		{
			name:       "POST /alerts/{id}/ack OPERATOR token -> 200 OK",
			method:     "POST",
			path:       "/api/v1/alerts/101/acknowledge",
			authHeader: "Bearer operator-tok",
			wantCode:   http.StatusOK,
		},
		{
			name:       "POST /alerts/{id}/ack ADMIN token -> 200 OK",
			method:     "POST",
			path:       "/api/v1/alerts/101/acknowledge",
			authHeader: "Bearer admin-tok",
			wantCode:   http.StatusOK,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, tc.path, nil)
			if tc.authHeader != "" {
				req.Header.Set("Authorization", tc.authHeader)
			}
			rec := httptest.NewRecorder()

			router.ServeHTTP(rec, req)

			if rec.Code != tc.wantCode {
				t.Fatalf("expected status %d, got %d (body: %s)", tc.wantCode, rec.Code, rec.Body.String())
			}
		})
	}
}
