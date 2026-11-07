package api_test

import (
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

func (m *mockChannelRepo) GetActiveAllocationByGateway(ctx context.Context, gatewayID string) (*domain.ChannelAllocation, error) {
	if err := domain.ValidateGatewayID(gatewayID); err != nil {
		return nil, err
	}
	if alloc, ok := m.allocs[gatewayID]; ok {
		return alloc, nil
	}
	return nil, domain.ErrAllocationNotFound
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
			return existing, nil // Idempotent replay
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
		req := httptest.NewRequest(http.MethodGet, "/api/v1/channels", nil)
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 OK, got %d: %s", rec.Code, rec.Body.String())
		}

		var channels []api.ChannelInfoDTO
		if err := json.Unmarshal(rec.Body.Bytes(), &channels); err != nil {
			t.Fatalf("unmarshal response: %v", err)
		}

		if len(channels) != domain.ChannelCountVN920 {
			t.Errorf("expected %d channels, got %d", domain.ChannelCountVN920, len(channels))
		}
		if channels[0].ChannelID != "CH00" || channels[0].FrequencyHz != 920250000 || channels[0].BandwidthHz != 125000 {
			t.Errorf("unexpected channel 0 info: %+v", channels[0])
		}
	})

	t.Run("invalid plan version query", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/channels?plan_version=UNKNOWN_PLAN", nil)
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
		body := `{"channel_id":"CH00"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/gateways/gw01/channels/request", strings.NewReader(body))
		req.Header.Set("X-Idempotency-Key", "req-1")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusCreated {
			t.Fatalf("expected 201 Created, got %d: %s", rec.Code, rec.Body.String())
		}

		var alloc api.ChannelAllocationDTO
		if err := json.Unmarshal(rec.Body.Bytes(), &alloc); err != nil {
			t.Fatalf("unmarshal response: %v", err)
		}
		if alloc.ChannelID != "CH00" || alloc.GatewayID != "gw01" || alloc.State != domain.StatusAllocated {
			t.Errorf("unexpected allocation: %+v", alloc)
		}
		if alloc.FrequencyHz != 920250000 || alloc.BandwidthHz != 125000 {
			t.Errorf("unexpected frequency or bandwidth: %+v", alloc)
		}
	})

	t.Run("missing idempotency key", func(t *testing.T) {
		body := `{"channel_id":"CH01"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/gateways/gw02/channels/request", strings.NewReader(body))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 Bad Request for missing idempotency key, got %d", rec.Code)
		}
	})

	t.Run("idempotent replay", func(t *testing.T) {
		body := `{"channel_id":"CH00"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/gateways/gw01/channels/request", strings.NewReader(body))
		req.Header.Set("X-Idempotency-Key", "req-1")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusCreated {
			t.Fatalf("expected 201 Created for idempotent request, got %d", rec.Code)
		}
	})

	t.Run("gateway already holds a channel", func(t *testing.T) {
		body := `{"channel_id":"CH01"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/gateways/gw01/channels/request", strings.NewReader(body))
		req.Header.Set("X-Idempotency-Key", "req-2")
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
		body := `{"channel_id":"CH00"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/gateways/gw02/channels/request", strings.NewReader(body))
		req.Header.Set("X-Idempotency-Key", "req-3")
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
		body := `{"channel_id":"CH99"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/gateways/gw02/channels/request", strings.NewReader(body))
		req.Header.Set("X-Idempotency-Key", "req-4")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusNotFound {
			t.Fatalf("expected 404 Not Found, got %d", rec.Code)
		}
	})

	t.Run("rejects unknown json fields (SE-004)", func(t *testing.T) {
		body := `{"channel_id":"CH01","injected":"evil"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/gateways/gw02/channels/request", strings.NewReader(body))
		req.Header.Set("X-Idempotency-Key", "req-5")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 Bad Request for unknown fields, got %d: %s", rec.Code, rec.Body.String())
		}
	})

	t.Run("rejects payload exceeding size limit", func(t *testing.T) {
		oversized := `{"channel_id":"CH01","filler":"` + strings.Repeat("x", 5000) + `"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/gateways/gw02/channels/request", strings.NewReader(oversized))
		req.Header.Set("X-Idempotency-Key", "req-6")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 Bad Request for oversized payload, got %d", rec.Code)
		}
	})
}

func TestGetChannelEndpoint(t *testing.T) {
	repo := newMockRepo()
	handler := api.NewChannelHandler(repo)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// Allocate CH02 to gw01
	_, err := repo.AllocateChannel(context.Background(), domain.AllocateRequest{
		GatewayID:          "gw01",
		ChannelID:          "CH02",
		ChannelPlanVersion: domain.ChannelPlanVN920V1,
		RequestID:          "req-alloc-1",
		GrantedBy:          "test",
	})
	if err != nil {
		t.Fatalf("setup allocation failed: %v", err)
	}

	t.Run("successful get assignment", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/gateways/gw01/channel", nil)
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 OK, got %d: %s", rec.Code, rec.Body.String())
		}

		var alloc api.ChannelAllocationDTO
		if err := json.Unmarshal(rec.Body.Bytes(), &alloc); err != nil {
			t.Fatalf("unmarshal response: %v", err)
		}
		if alloc.GatewayID != "gw01" || alloc.ChannelID != "CH02" || alloc.State != domain.StatusAllocated {
			t.Errorf("unexpected allocation: %+v", alloc)
		}
	})

	t.Run("channel not allocated", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/gateways/gw99/channel", nil)
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusNotFound {
			t.Fatalf("expected 404 Not Found, got %d", rec.Code)
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
		req := httptest.NewRequest(http.MethodDelete, "/api/v1/gateways/gw01/channel", nil)
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 OK, got %d: %s", rec.Code, rec.Body.String())
		}

		var rel api.ChannelReleaseResponseDTO
		if err := json.Unmarshal(rec.Body.Bytes(), &rel); err != nil {
			t.Fatalf("unmarshal response: %v", err)
		}
		if rel.Status != domain.StatusReleased || rel.GatewayID != "gw01" || rel.ChannelID != "CH01" {
			t.Errorf("unexpected released alloc: %+v", rel)
		}
	})

	t.Run("release non-allocated channel", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodDelete, "/api/v1/gateways/gw01/channel", nil)
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusNotFound {
			t.Fatalf("expected 404 Not Found, got %d: %s", rec.Code, rec.Body.String())
		}
	})
}
