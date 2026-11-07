package api_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockChannelRepo struct {
	storage.ChannelRepository
	channels []domain.ChannelView
	allocs   map[string]*domain.ChannelAllocation // key: gateway_id
	chanMap  map[string]*domain.ChannelAllocation // key: channel_id
}

func newMockRepo() *mockChannelRepo {
	var views []domain.ChannelView
	for i := 0; i < domain.ChannelCountVN920; i++ {
		chID := "CH" + string([]byte{byte('0' + i/10), byte('0' + i%10)})
		freq, _ := domain.GetApprovedFrequencyHz(chID)
		views = append(views, domain.ChannelView{
			ChannelID:          chID,
			ChannelPlanVersion: domain.ChannelPlanVN920V1,
			CenterFrequencyHz:  freq,
			BandwidthHz:        domain.DefaultBandwidthHz,
			IsEnabled:          true,
			State:              domain.StatusAvailable,
		})
	}
	return &mockChannelRepo{
		channels: views,
		allocs:   make(map[string]*domain.ChannelAllocation),
		chanMap:  make(map[string]*domain.ChannelAllocation),
	}
}

func (m *mockChannelRepo) ListChannels(ctx context.Context, planVersion string) ([]domain.ChannelView, error) {
	if planVersion != domain.ChannelPlanVN920V1 {
		return nil, domain.ErrInvalidChannelPlan
	}
	res := make([]domain.ChannelView, len(m.channels))
	copy(res, m.channels)
	for i := range res {
		if _, ok := m.chanMap[res[i].ChannelID]; ok {
			res[i].State = domain.StatusAllocated
		}
	}
	return res, nil
}

func (m *mockChannelRepo) AllocateChannel(ctx context.Context, req domain.AllocateRequest) (*domain.ChannelAllocation, error) {
	if err := domain.ValidateGatewayID(req.GatewayID); err != nil {
		return nil, err
	}
	if err := domain.ValidateChannelID(req.ChannelID); err != nil {
		return nil, err
	}
	if err := domain.ValidateChannelPlanVersion(req.ChannelPlanVersion); err != nil {
		return nil, err
	}
	if err := domain.ValidateRequestID(req.RequestID); err != nil {
		return nil, err
	}

	if existing, ok := m.allocs[req.GatewayID]; ok {
		if existing.RequestID == req.RequestID && existing.ChannelID == req.ChannelID {
			return existing, nil // Idempotent
		}
		return nil, domain.ErrGatewayAlreadyAllocated
	}

	if _, occupied := m.chanMap[req.ChannelID]; occupied {
		return nil, domain.ErrChannelInUse
	}

	alloc := &domain.ChannelAllocation{
		ID:                   int64(len(m.allocs) + 1),
		GatewayID:            req.GatewayID,
		ChannelID:            req.ChannelID,
		Status:               domain.StatusAllocated,
		RequestID:            req.RequestID,
		AllocationGeneration: 1,
		GrantedBy:            req.GrantedBy,
		CreatedAt:            time.Now().UTC(),
		UpdatedAt:            time.Now().UTC(),
	}
	m.allocs[req.GatewayID] = alloc
	m.chanMap[req.ChannelID] = alloc
	return alloc, nil
}

func (m *mockChannelRepo) ReleaseChannel(ctx context.Context, req domain.ReleaseRequest) (*domain.ChannelAllocation, error) {
	if err := domain.ValidateGatewayID(req.GatewayID); err != nil {
		return nil, err
	}
	if err := domain.ValidateChannelID(req.ChannelID); err != nil {
		return nil, err
	}
	if err := domain.ValidateRequestID(req.RequestID); err != nil {
		return nil, err
	}

	alloc, ok := m.allocs[req.GatewayID]
	if !ok || alloc.ChannelID != req.ChannelID {
		return nil, domain.ErrAllocationNotFound
	}

	alloc.Status = domain.StatusReleased
	alloc.ReleasedBy = req.ReleasedBy
	alloc.ReleaseReason = req.ReleaseReason
	now := time.Now().UTC()
	alloc.ReleasedAt = &now
	alloc.UpdatedAt = now

	delete(m.allocs, req.GatewayID)
	delete(m.chanMap, req.ChannelID)
	return alloc, nil
}

func TestListChannelsEndpoint(t *testing.T) {
	repo := newMockRepo()
	handler := api.NewChannelHandler(repo)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	t.Run("default plan version", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/rf/channels", nil)
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 OK, got %d: %s", rec.Code, rec.Body.String())
		}

		var resp api.ChannelListResponseDTO
		if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
			t.Fatalf("unmarshal response: %v", err)
		}

		if resp.ChannelPlanVersion != domain.ChannelPlanVN920V1 {
			t.Errorf("expected plan %s, got %s", domain.ChannelPlanVN920V1, resp.ChannelPlanVersion)
		}
		if len(resp.Channels) != domain.ChannelCountVN920 {
			t.Errorf("expected %d channels, got %d", domain.ChannelCountVN920, len(resp.Channels))
		}
		if !strings.Contains(resp.RegulatoryNotice, "ERP") {
			t.Errorf("missing regulatory notice in response")
		}
	})

	t.Run("invalid plan version query", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/rf/channels?plan_version=UNKNOWN_PLAN", nil)
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 Bad Request, got %d", rec.Code)
		}
	})
}

func TestAllocateChannelEndpoint(t *testing.T) {
	repo := newMockRepo()
	handler := api.NewChannelHandler(repo)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	t.Run("successful allocation", func(t *testing.T) {
		body := `{"gateway_id":"gw01","channel_id":"CH00","channel_plan_version":"VN920_V1","request_id":"req-1"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/rf/channels/allocate", strings.NewReader(body))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 OK, got %d: %s", rec.Code, rec.Body.String())
		}

		var alloc domain.ChannelAllocation
		if err := json.Unmarshal(rec.Body.Bytes(), &alloc); err != nil {
			t.Fatalf("unmarshal response: %v", err)
		}
		if alloc.ChannelID != "CH00" || alloc.GatewayID != "gw01" || alloc.Status != domain.StatusAllocated {
			t.Errorf("unexpected allocation: %+v", alloc)
		}
	})

	t.Run("idempotent replay", func(t *testing.T) {
		body := `{"gateway_id":"gw01","channel_id":"CH00","channel_plan_version":"VN920_V1","request_id":"req-1"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/rf/channels/allocate", strings.NewReader(body))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 OK for idempotent request, got %d", rec.Code)
		}
	})

	t.Run("gateway already holds a channel", func(t *testing.T) {
		body := `{"gateway_id":"gw01","channel_id":"CH01","channel_plan_version":"VN920_V1","request_id":"req-2"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/rf/channels/allocate", strings.NewReader(body))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusConflict {
			t.Fatalf("expected 409 Conflict, got %d: %s", rec.Code, rec.Body.String())
		}
		if !strings.Contains(rec.Body.String(), "GATEWAY_ALREADY_ALLOCATED") {
			t.Errorf("expected GATEWAY_ALREADY_ALLOCATED, got %s", rec.Body.String())
		}
	})

	t.Run("channel already in use by another gateway", func(t *testing.T) {
		body := `{"gateway_id":"gw02","channel_id":"CH00","channel_plan_version":"VN920_V1","request_id":"req-3"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/rf/channels/allocate", strings.NewReader(body))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusConflict {
			t.Fatalf("expected 409 Conflict, got %d: %s", rec.Code, rec.Body.String())
		}
		if !strings.Contains(rec.Body.String(), "CHANNEL_IN_USE") {
			t.Errorf("expected CHANNEL_IN_USE, got %s", rec.Body.String())
		}
	})

	t.Run("invalid channel", func(t *testing.T) {
		body := `{"gateway_id":"gw02","channel_id":"CH99","channel_plan_version":"VN920_V1","request_id":"req-4"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/rf/channels/allocate", strings.NewReader(body))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusNotFound {
			t.Fatalf("expected 404 Not Found, got %d", rec.Code)
		}
	})

	t.Run("rejects unknown json fields (SE-004)", func(t *testing.T) {
		body := `{"gateway_id":"gw02","channel_id":"CH01","channel_plan_version":"VN920_V1","request_id":"req-5","injected":"evil"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/rf/channels/allocate", strings.NewReader(body))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 Bad Request for unknown fields, got %d: %s", rec.Code, rec.Body.String())
		}
	})

	t.Run("rejects payload exceeding size limit", func(t *testing.T) {
		oversized := `{"gateway_id":"gw02","channel_id":"CH01","channel_plan_version":"VN920_V1","request_id":"` + strings.Repeat("x", 5000) + `"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/rf/channels/allocate", strings.NewReader(oversized))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 Bad Request for oversized payload, got %d", rec.Code)
		}
	})
}

func TestReleaseChannelEndpoint(t *testing.T) {
	repo := newMockRepo()
	handler := api.NewChannelHandler(repo)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// First allocate CH01 to gw01
	_, err := repo.AllocateChannel(context.Background(), domain.AllocateRequest{
		GatewayID:          "gw01",
		ChannelID:          "CH01",
		ChannelPlanVersion: domain.ChannelPlanVN920V1,
		RequestID:          "req-alloc-1",
		GrantedBy:          "test",
	})
	if err != nil {
		t.Fatalf("setup allocation failed: %v", err)
	}

	t.Run("successful release", func(t *testing.T) {
		body := `{"gateway_id":"gw01","channel_id":"CH01","request_id":"req-rel-1","reason":"schedule_deactivated"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/rf/channels/release", bytes.NewBufferString(body))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 OK, got %d: %s", rec.Code, rec.Body.String())
		}

		var alloc domain.ChannelAllocation
		if err := json.Unmarshal(rec.Body.Bytes(), &alloc); err != nil {
			t.Fatalf("unmarshal response: %v", err)
		}
		if alloc.Status != domain.StatusReleased || alloc.ReleaseReason != "schedule_deactivated" {
			t.Errorf("unexpected released alloc: %+v", alloc)
		}
	})

	t.Run("release non-allocated channel", func(t *testing.T) {
		body := `{"gateway_id":"gw01","channel_id":"CH01","request_id":"req-rel-2"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/rf/channels/release", bytes.NewBufferString(body))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusNotFound {
			t.Fatalf("expected 404 Not Found, got %d: %s", rec.Code, rec.Body.String())
		}
	})
}
