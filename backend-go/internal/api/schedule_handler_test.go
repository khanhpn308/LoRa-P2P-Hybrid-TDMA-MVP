package api_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
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
func (m *mockChannelRepoForSchedule) ListChannels(ctx context.Context, planVersion string) ([]domain.ChannelView, error) {
	return nil, nil
}
func (m *mockChannelRepoForSchedule) AllocateChannel(ctx context.Context, req domain.AllocateRequest) (*domain.ChannelAllocation, error) {
	return nil, nil
}
func (m *mockChannelRepoForSchedule) ReleaseChannel(ctx context.Context, req domain.ReleaseRequest) (*domain.ChannelAllocation, error) {
	return nil, nil
}
func (m *mockChannelRepoForSchedule) GetActiveAllocationByChannel(ctx context.Context, channelID string) (*domain.ChannelAllocation, error) {
	return nil, nil
}
func (m *mockChannelRepoForSchedule) GetActiveAllocationByGateway(ctx context.Context, gatewayID string) (*domain.ChannelAllocation, error) {
	if a, ok := m.allocations[gatewayID]; ok && a.Status == domain.StatusAllocated {
		return a, nil
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

type mockScheduleDispatcherForAPI struct {
	dispatchedSched *scheduler.Schedule
	dispatchErr     error
}

func (m *mockScheduleDispatcherForAPI) DispatchSchedule(ctx context.Context, sched *scheduler.Schedule) error {
	if m.dispatchErr != nil {
		return m.dispatchErr
	}
	m.dispatchedSched = sched
	return nil
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

func setupScheduleHandlerWithDeps() (*api.ScheduleHandler, *mockChannelRepoForSchedule, *scheduler.MemoryScheduleRepository, *mockScheduleDispatcherForAPI, *api.StaticAuthenticator) {
	channelRepo := &mockChannelRepoForSchedule{
		allocations: make(map[string]*domain.ChannelAllocation),
	}
	scheduleRepo := scheduler.NewMemoryScheduleRepository()
	validator := scheduler.NewFeasibilityValidator(nil)
	planner := scheduler.NewPlanner(validator)
	disp := &mockScheduleDispatcherForAPI{}

	tokens := map[string]api.Role{
		"admin-token":    api.RoleAdmin,
		"operator-token": api.RoleOperator,
		"viewer-token":   api.RoleViewer,
	}
	auth := api.NewStaticAuthenticator(tokens)

	handler := api.NewScheduleHandlerWithDeps(scheduleRepo, channelRepo, planner, disp, auth)
	return handler, channelRepo, scheduleRepo, disp, auth
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

func TestScheduleHandler_ActivationRequest_Table(t *testing.T) {
	tests := []struct {
		name                 string
		gwID                 string
		schedID              string
		idempotencyKey       string
		authHeader           string
		body                 string
		setupChannel         bool
		preReviewState       string
		dispatcherErr        error
		expectedStatus       int
		expectedState        string
		expectedReviewState  string
		checkDispatcherCalls bool
	}{
		{
			name:                 "success activation request with approved schedule and channel allocation",
			gwID:                 "gw01",
			schedID:              "100",
			idempotencyKey:       "idemp-key-1",
			authHeader:           "Bearer admin-token",
			body:                 `{"expected_version": 1}`,
			setupChannel:         true,
			preReviewState:       "APPROVED",
			expectedStatus:       http.StatusAccepted,
			expectedState:        "SENT",
			expectedReviewState:  "APPROVED",
			checkDispatcherCalls: true,
		},
		{
			name:           "missing idempotency key header returns 422",
			gwID:           "gw01",
			schedID:        "100",
			idempotencyKey: "",
			authHeader:     "Bearer admin-token",
			body:           `{"expected_version": 1}`,
			setupChannel:   true,
			preReviewState: "APPROVED",
			expectedStatus: http.StatusUnprocessableEntity,
		},
		{
			name:           "missing expected_version in body returns 422",
			gwID:           "gw01",
			schedID:        "100",
			idempotencyKey: "idemp-key-2",
			authHeader:     "Bearer admin-token",
			body:           `{}`,
			setupChannel:   true,
			preReviewState: "APPROVED",
			expectedStatus: http.StatusUnprocessableEntity,
		},
		{
			name:           "version mismatch returns 409",
			gwID:           "gw01",
			schedID:        "100",
			idempotencyKey: "idemp-key-3",
			authHeader:     "Bearer admin-token",
			body:           `{"expected_version": 99}`,
			setupChannel:   true,
			preReviewState: "APPROVED",
			expectedStatus: http.StatusConflict,
		},
		{
			name:           "unapproved schedule in PENDING review state returns 409",
			gwID:           "gw01",
			schedID:        "100",
			idempotencyKey: "idemp-key-4",
			authHeader:     "Bearer admin-token",
			body:           `{"expected_version": 1}`,
			setupChannel:   true,
			preReviewState: "PENDING",
			expectedStatus: http.StatusConflict,
		},
		{
			name:           "rejected schedule returns 409",
			gwID:           "gw01",
			schedID:        "100",
			idempotencyKey: "idemp-key-5",
			authHeader:     "Bearer admin-token",
			body:           `{"expected_version": 1}`,
			setupChannel:   true,
			preReviewState: "REJECTED",
			expectedStatus: http.StatusConflict,
		},
		{
			name:           "missing channel allocation returns 409",
			gwID:           "gw01",
			schedID:        "100",
			idempotencyKey: "idemp-key-6",
			authHeader:     "Bearer admin-token",
			body:           `{"expected_version": 1}`,
			setupChannel:   false,
			preReviewState: "APPROVED",
			expectedStatus: http.StatusConflict,
		},
		{
			name:           "missing bearer token returns 401",
			gwID:           "gw01",
			schedID:        "100",
			idempotencyKey: "idemp-key-7",
			authHeader:     "",
			body:           `{"expected_version": 1}`,
			setupChannel:   true,
			preReviewState: "APPROVED",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "non-ADMIN operator role returns 403",
			gwID:           "gw01",
			schedID:        "100",
			idempotencyKey: "idemp-key-8",
			authHeader:     "Bearer operator-token",
			body:           `{"expected_version": 1}`,
			setupChannel:   true,
			preReviewState: "APPROVED",
			expectedStatus: http.StatusForbidden,
		},
		{
			name:           "dispatcher failure propagates 500",
			gwID:           "gw01",
			schedID:        "100",
			idempotencyKey: "idemp-key-9",
			authHeader:     "Bearer admin-token",
			body:           `{"expected_version": 1}`,
			setupChannel:   true,
			preReviewState: "APPROVED",
			dispatcherErr:  errors.New("mqtt timeout"),
			expectedStatus: http.StatusInternalServerError,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			handler, channelRepo, scheduleRepo, disp, _ := setupScheduleHandlerWithDeps()
			disp.dispatchErr = tt.dispatcherErr

			if tt.setupChannel {
				channelRepo.allocations[tt.gwID] = &domain.ChannelAllocation{
					GatewayID:            tt.gwID,
					ChannelID:            "CH00",
					Status:               domain.StatusAllocated,
					AllocationGeneration: 1,
					CreatedAt:            time.Now().UTC(),
				}
			}

			// Pre-populate schedule
			sched := &scheduler.Schedule{
				SchemaVersion:          scheduler.DefaultSchemaVersion,
				RequestID:              "550e8400-e29b-41d4-a716-446655440000",
				GatewayID:              tt.gwID,
				ScheduleID:             tt.schedID,
				ScheduleVersion:        1,
				ScheduleGeneration:     1,
				CreatedAt:              time.Now().UTC(),
				ExpiresAt:              time.Now().UTC().Add(24 * time.Hour),
				ProfileID:              scheduler.ProfileV2VN920Static15N,
				SuperframeMs:           9000,
				MinAnnounceSuperframes: 3,
				ChannelID:              "CH00",
				NetworkID:              1,
				Slots: []scheduler.SlotConfig{
					{NodeID: 1, SlotID: 1, OffsetMs: 50, DurationMs: 500},
				},
				AffectedNodeSet: []uint8{1},
			}
			_ = scheduleRepo.SaveSchedule(context.Background(), sched)
			_ = scheduleRepo.UpdateReviewState(context.Background(), tt.schedID, tt.preReviewState, nil)

			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)

			url := fmt.Sprintf("/api/v1/gateways/%s/schedules/%s/activation-requests", tt.gwID, tt.schedID)
			req := httptest.NewRequest("POST", url, bytes.NewBufferString(tt.body))
			req.Header.Set("Content-Type", "application/json")
			if tt.idempotencyKey != "" {
				req.Header.Set("X-Idempotency-Key", tt.idempotencyKey)
			}
			if tt.authHeader != "" {
				req.Header.Set("Authorization", tt.authHeader)
			}

			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Fatalf("expected status %d, got %d (%s)", tt.expectedStatus, rec.Code, rec.Body.String())
			}

			if tt.expectedStatus == http.StatusAccepted {
				var summary api.ScheduleSummaryDTO
				if err := json.Unmarshal(rec.Body.Bytes(), &summary); err != nil {
					t.Fatalf("failed to decode response: %v", err)
				}
				if summary.State != tt.expectedState {
					t.Errorf("got state %s, want %s", summary.State, tt.expectedState)
				}
				if summary.ReviewState == nil || *summary.ReviewState != tt.expectedReviewState {
					t.Errorf("got review state %v, want %s", summary.ReviewState, tt.expectedReviewState)
				}
				if tt.checkDispatcherCalls && disp.dispatchedSched == nil {
					t.Error("expected dispatcher.DispatchSchedule to be called, got nil")
				}
			}
		})
	}
}

func TestScheduleHandler_ActivationRequest_Idempotency(t *testing.T) {
	handler, channelRepo, scheduleRepo, disp, _ := setupScheduleHandlerWithDeps()

	gwID := "gw01"
	schedID := "100"
	channelRepo.allocations[gwID] = &domain.ChannelAllocation{
		GatewayID:            gwID,
		ChannelID:            "CH00",
		Status:               domain.StatusAllocated,
		AllocationGeneration: 1,
		CreatedAt:            time.Now().UTC(),
	}

	sched := &scheduler.Schedule{
		SchemaVersion:          scheduler.DefaultSchemaVersion,
		RequestID:              "550e8400-e29b-41d4-a716-446655440000",
		GatewayID:              gwID,
		ScheduleID:             schedID,
		ScheduleVersion:        1,
		ScheduleGeneration:     1,
		CreatedAt:              time.Now().UTC(),
		ExpiresAt:              time.Now().UTC().Add(24 * time.Hour),
		ProfileID:              scheduler.ProfileV2VN920Static15N,
		SuperframeMs:           9000,
		MinAnnounceSuperframes: 3,
		ChannelID:              "CH00",
		NetworkID:              1,
		Slots: []scheduler.SlotConfig{
			{NodeID: 1, SlotID: 1, OffsetMs: 50, DurationMs: 500},
		},
		AffectedNodeSet: []uint8{1},
	}
	_ = scheduleRepo.SaveSchedule(context.Background(), sched)
	_ = scheduleRepo.UpdateReviewState(context.Background(), schedID, "APPROVED", nil)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	url := fmt.Sprintf("/api/v1/gateways/%s/schedules/%s/activation-requests", gwID, schedID)

	// First submission: success 202
	body := `{"expected_version": 1}`
	req1 := httptest.NewRequest("POST", url, bytes.NewBufferString(body))
	req1.Header.Set("Content-Type", "application/json")
	req1.Header.Set("X-Idempotency-Key", "idemp-key-stable")
	req1.Header.Set("Authorization", "Bearer admin-token")
	rec1 := httptest.NewRecorder()
	mux.ServeHTTP(rec1, req1)

	if rec1.Code != http.StatusAccepted {
		t.Fatalf("first request expected 202, got: %d (%s)", rec1.Code, rec1.Body.String())
	}

	// Second identical submission: returns cached 202
	req2 := httptest.NewRequest("POST", url, bytes.NewBufferString(body))
	req2.Header.Set("Content-Type", "application/json")
	req2.Header.Set("X-Idempotency-Key", "idemp-key-stable")
	req2.Header.Set("Authorization", "Bearer admin-token")
	rec2 := httptest.NewRecorder()
	mux.ServeHTTP(rec2, req2)

	if rec2.Code != http.StatusAccepted {
		t.Fatalf("second identical request expected 202, got: %d (%s)", rec2.Code, rec2.Body.String())
	}

	// Third conflicting submission with same key but different version: returns 409 Conflict
	conflictingBody := `{"expected_version": 2}`
	req3 := httptest.NewRequest("POST", url, bytes.NewBufferString(conflictingBody))
	req3.Header.Set("Content-Type", "application/json")
	req3.Header.Set("X-Idempotency-Key", "idemp-key-stable")
	req3.Header.Set("Authorization", "Bearer admin-token")
	rec3 := httptest.NewRecorder()
	mux.ServeHTTP(rec3, req3)

	if rec3.Code != http.StatusConflict {
		t.Fatalf("conflicting request expected 409 Conflict, got: %d (%s)", rec3.Code, rec3.Body.String())
	}

	_ = disp
}

func TestScheduleHandler_RBAC_Roles(t *testing.T) {
	handler, channelRepo, scheduleRepo, _, _ := setupScheduleHandlerWithDeps()

	gwID := "gw01"
	schedID := "100"
	channelRepo.allocations[gwID] = &domain.ChannelAllocation{
		GatewayID:            gwID,
		ChannelID:            "CH00",
		Status:               domain.StatusAllocated,
		AllocationGeneration: 1,
		CreatedAt:            time.Now().UTC(),
	}

	sched := &scheduler.Schedule{
		SchemaVersion:          scheduler.DefaultSchemaVersion,
		RequestID:              "550e8400-e29b-41d4-a716-446655440000",
		GatewayID:              gwID,
		ScheduleID:             schedID,
		ScheduleVersion:        1,
		ScheduleGeneration:     1,
		CreatedAt:              time.Now().UTC(),
		ExpiresAt:              time.Now().UTC().Add(24 * time.Hour),
		ProfileID:              scheduler.ProfileV2VN920Static15N,
		SuperframeMs:           9000,
		MinAnnounceSuperframes: 3,
		ChannelID:              "CH00",
		NetworkID:              1,
		Slots: []scheduler.SlotConfig{
			{NodeID: 1, SlotID: 1, OffsetMs: 50, DurationMs: 500},
		},
		AffectedNodeSet: []uint8{1},
	}
	_ = scheduleRepo.SaveSchedule(context.Background(), sched)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// VIEWER can GET schedule
	getReq := httptest.NewRequest("GET", fmt.Sprintf("/api/v1/gateways/%s/schedules/%s", gwID, schedID), nil)
	getReq.Header.Set("Authorization", "Bearer viewer-token")
	getRec := httptest.NewRecorder()
	mux.ServeHTTP(getRec, getReq)

	if getRec.Code != http.StatusOK {
		t.Fatalf("VIEWER expected 200 OK on GET schedule, got: %d", getRec.Code)
	}

	// VIEWER forbidden on review
	revReq := httptest.NewRequest("POST", fmt.Sprintf("/api/v1/gateways/%s/schedules/%s/review", gwID, schedID), bytes.NewBufferString(`{"decision":"APPROVE"}`))
	revReq.Header.Set("Authorization", "Bearer viewer-token")
	revRec := httptest.NewRecorder()
	mux.ServeHTTP(revRec, revReq)

	if revRec.Code != http.StatusForbidden {
		t.Fatalf("VIEWER expected 403 Forbidden on review, got: %d", revRec.Code)
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
