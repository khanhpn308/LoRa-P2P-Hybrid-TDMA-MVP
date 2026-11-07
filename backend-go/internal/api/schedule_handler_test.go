package api_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

type mockChannelRepoForSchedule struct {
	allocations map[string]*domain.ChannelAllocation
}

func (m *mockChannelRepoForSchedule) GetChannel(ctx context.Context, channelID string) (*domain.RFChannel, error) {
	return nil, nil
}
func (m *mockChannelRepoForSchedule) ListChannels(ctx context.Context, version string) ([]domain.ChannelView, error) {
	return nil, nil
}
func (m *mockChannelRepoForSchedule) AllocateChannel(ctx context.Context, req domain.AllocateRequest) (*domain.ChannelAllocation, error) {
	return nil, nil
}
func (m *mockChannelRepoForSchedule) ReleaseChannel(ctx context.Context, req domain.ReleaseRequest) (*domain.ChannelAllocation, error) {
	return nil, nil
}
func (m *mockChannelRepoForSchedule) GetActiveAllocationByGateway(ctx context.Context, gatewayID string) (*domain.ChannelAllocation, error) {
	if alloc, ok := m.allocations[gatewayID]; ok {
		return alloc, nil
	}
	return nil, domain.ErrAllocationNotFound
}
func (m *mockChannelRepoForSchedule) GetActiveAllocationByChannel(ctx context.Context, channelID string) (*domain.ChannelAllocation, error) {
	for _, alloc := range m.allocations {
		if alloc.ChannelID == channelID {
			return alloc, nil
		}
	}
	return nil, domain.ErrAllocationNotFound
}
func (m *mockChannelRepoForSchedule) ListActiveAllocations(ctx context.Context) ([]domain.ChannelAllocation, error) {
	var list []domain.ChannelAllocation
	for _, alloc := range m.allocations {
		list = append(list, *alloc)
	}
	return list, nil
}

func setupScheduleHandler() (*api.ScheduleHandler, *mockChannelRepoForSchedule, *scheduler.MemoryScheduleRepository) {
	channelRepo := &mockChannelRepoForSchedule{
		allocations: make(map[string]*domain.ChannelAllocation),
	}
	scheduleRepo := scheduler.NewMemoryScheduleRepository()
	validator := scheduler.NewFeasibilityValidator(nil)
	planner := scheduler.NewPlanner(validator)
	handler := api.NewScheduleHandler(scheduleRepo, channelRepo, planner)
	return handler, channelRepo, scheduleRepo
}

func TestScheduleHandler_GenerateSchedule_Success(t *testing.T) {
	handler, channelRepo, _ := setupScheduleHandler()

	channelRepo.allocations["gw01"] = &domain.ChannelAllocation{
		GatewayID:            "gw01",
		ChannelID:            "CH00",
		Status:               domain.StatusAllocated,
		AllocationGeneration: 1,
		CreatedAt:            time.Now().UTC(),
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	body := `{"profile_id":"V2-VN920-STATIC-15N"}`
	req := httptest.NewRequest("POST", "/api/v1/gateways/gw01/schedules/generate", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202 Accepted, got: %d (%s)", rec.Code, rec.Body.String())
	}

	var summary api.ScheduleSummaryDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &summary); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if summary.GatewayID != "gw01" || summary.State != "PROPOSED" {
		t.Fatalf("unexpected summary: %+v", summary)
	}
	if summary.ReviewState == nil || *summary.ReviewState != "PENDING" {
		t.Fatalf("expected review_state=PENDING, got: %v", summary.ReviewState)
	}
}

func TestScheduleHandler_GenerateSchedule_ChannelNotAllocated(t *testing.T) {
	handler, _, _ := setupScheduleHandler()

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	body := `{"profile_id":"V2-VN920-STATIC-15N"}`
	req := httptest.NewRequest("POST", "/api/v1/gateways/gw02/schedules/generate", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409 Conflict when channel not allocated, got: %d", rec.Code)
	}
}

func TestScheduleHandler_GenerateSchedule_InvalidProfile(t *testing.T) {
	handler, channelRepo, _ := setupScheduleHandler()

	channelRepo.allocations["gw01"] = &domain.ChannelAllocation{
		GatewayID: "gw01",
		ChannelID: "CH00",
		Status:    domain.StatusAllocated,
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	body := `{"profile_id":"INVALID-PROFILE"}`
	req := httptest.NewRequest("POST", "/api/v1/gateways/gw01/schedules/generate", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()

	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422 Unprocessable Entity, got: %d", rec.Code)
	}
}

func TestScheduleHandler_GetAndReviewSchedule(t *testing.T) {
	handler, channelRepo, _ := setupScheduleHandler()

	channelRepo.allocations["gw01"] = &domain.ChannelAllocation{
		GatewayID: "gw01",
		ChannelID: "CH00",
		Status:    domain.StatusAllocated,
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// 1. Generate schedule
	body := `{"profile_id":"V2-VN920-STATIC-15N"}`
	genReq := httptest.NewRequest("POST", "/api/v1/gateways/gw01/schedules/generate", bytes.NewBufferString(body))
	genRec := httptest.NewRecorder()
	mux.ServeHTTP(genRec, genReq)

	var genSummary api.ScheduleSummaryDTO
	_ = json.Unmarshal(genRec.Body.Bytes(), &genSummary)
	schedID := genSummary.ScheduleID

	// 2. Get schedule
	getReq := httptest.NewRequest("GET", "/api/v1/gateways/gw01/schedules/"+schedID, nil)
	getRec := httptest.NewRecorder()
	mux.ServeHTTP(getRec, getReq)

	if getRec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK for GetSchedule, got: %d", getRec.Code)
	}

	// 3. Review schedule: APPROVE
	revBody := `{"decision":"APPROVE","note":"maintenance approved"}`
	revReq := httptest.NewRequest("POST", "/api/v1/gateways/gw01/schedules/"+schedID+"/review", bytes.NewBufferString(revBody))
	revReq.Header.Set("Content-Type", "application/json")
	revRec := httptest.NewRecorder()
	mux.ServeHTTP(revRec, revReq)

	if revRec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK for ReviewSchedule, got: %d", revRec.Code)
	}

	var revSummary api.ScheduleSummaryDTO
	_ = json.Unmarshal(revRec.Body.Bytes(), &revSummary)
	if revSummary.ReviewState == nil || *revSummary.ReviewState != "APPROVED" {
		t.Fatalf("expected ReviewState=APPROVED, got: %v", revSummary.ReviewState)
	}
}

func TestScheduleHandler_ConcurrentAccess(t *testing.T) {
	handler, channelRepo, _ := setupScheduleHandler()

	channelRepo.allocations["gw01"] = &domain.ChannelAllocation{
		GatewayID:            "gw01",
		ChannelID:            "CH00",
		Status:               domain.StatusAllocated,
		AllocationGeneration: 1,
		CreatedAt:            time.Now().UTC(),
	}

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// Pre-generate a schedule
	body := `{"profile_id":"V2-VN920-STATIC-15N"}`
	genReq := httptest.NewRequest("POST", "/api/v1/gateways/gw01/schedules/generate", bytes.NewBufferString(body))
	genRec := httptest.NewRecorder()
	mux.ServeHTTP(genRec, genReq)

	var genSummary api.ScheduleSummaryDTO
	_ = json.Unmarshal(genRec.Body.Bytes(), &genSummary)
	schedID := genSummary.ScheduleID

	const goroutines = 20
	var wg sync.WaitGroup
	wg.Add(goroutines * 3)

	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			req := httptest.NewRequest("GET", "/api/v1/gateways/gw01/schedules/"+schedID, nil)
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)
		}()
		go func() {
			defer wg.Done()
			rBody := `{"decision":"APPROVE","note":"concurrency test"}`
			req := httptest.NewRequest("POST", "/api/v1/gateways/gw01/schedules/"+schedID+"/review", bytes.NewBufferString(rBody))
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)
		}()
		go func() {
			defer wg.Done()
			gBody := `{"profile_id":"V2-VN920-STATIC-15N"}`
			req := httptest.NewRequest("POST", "/api/v1/gateways/gw01/schedules/generate", bytes.NewBufferString(gBody))
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)
		}()
	}

	wg.Wait()
}
