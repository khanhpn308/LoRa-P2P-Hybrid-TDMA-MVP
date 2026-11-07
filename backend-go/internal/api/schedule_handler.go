package api

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var scheduleIDRegex = regexp.MustCompile(`^(0|[1-9][0-9]{0,19})$`)

// ScheduleSummaryDTO matches the ScheduleSummary component schema in openapi.yaml.
type ScheduleSummaryDTO struct {
	ScheduleID              string  `json:"schedule_id"`
	GatewayID               string  `json:"gateway_id"`
	Version                 int64   `json:"version"`
	State                   string  `json:"state"`
	ActivateAtSuperframeSeq *int64  `json:"activate_at_superframe_seq"`
	CreatedAt               string  `json:"created_at"`
	ActivatedAt             *string `json:"activated_at"`
	RejectReason            *string `json:"reject_reason,omitempty"`
	ReviewState             *string `json:"review_state,omitempty"`
}

// GenerateScheduleRequestDTO matches GenerateScheduleRequest in openapi.yaml.
type GenerateScheduleRequestDTO struct {
	ProfileID              string `json:"profile_id"`
	MinAnnounceSuperframes *int   `json:"min_announce_superframes,omitempty"`
}

// ScheduleReviewRequestDTO matches ScheduleReviewRequest in openapi.yaml.
type ScheduleReviewRequestDTO struct {
	Decision string `json:"decision"`
	Note     string `json:"note,omitempty"`
	Comment  string `json:"comment,omitempty"`
}

// ScheduleActivationRequestDTO matches ScheduleActivationRequest in openapi.yaml.
type ScheduleActivationRequestDTO struct {
	ExpectedVersion *uint32 `json:"expected_version"`
}

// ScheduleDispatcherInterface defines the schedule dispatch contract.
type ScheduleDispatcherInterface interface {
	DispatchSchedule(ctx context.Context, sched *scheduler.Schedule) error
}

type idempotentActivationRecord struct {
	ExpectedVersion uint32
	Response        ScheduleSummaryDTO
}

// ScheduleHandler provides HTTP REST endpoints for schedule planning, review, and activation dispatch.
type ScheduleHandler struct {
	mu             sync.RWMutex
	scheduleRepo   scheduler.ScheduleRepository
	channelRepo    storage.ChannelRepository
	planner        *scheduler.Planner
	dispatcher     ScheduleDispatcherInterface
	authenticator  Authenticator
	idempotencyMap map[string]*idempotentActivationRecord
}

// NewScheduleHandler creates a new ScheduleHandler with base dependencies.
func NewScheduleHandler(
	scheduleRepo scheduler.ScheduleRepository,
	channelRepo storage.ChannelRepository,
	planner *scheduler.Planner,
) *ScheduleHandler {
	return &ScheduleHandler{
		scheduleRepo:   scheduleRepo,
		channelRepo:    channelRepo,
		planner:        planner,
		idempotencyMap: make(map[string]*idempotentActivationRecord),
	}
}

// NewScheduleHandlerWithDeps creates a new ScheduleHandler with dispatcher and authenticator dependencies.
func NewScheduleHandlerWithDeps(
	scheduleRepo scheduler.ScheduleRepository,
	channelRepo storage.ChannelRepository,
	planner *scheduler.Planner,
	dispatcher ScheduleDispatcherInterface,
	authenticator Authenticator,
) *ScheduleHandler {
	return &ScheduleHandler{
		scheduleRepo:   scheduleRepo,
		channelRepo:    channelRepo,
		planner:        planner,
		dispatcher:     dispatcher,
		authenticator:  authenticator,
		idempotencyMap: make(map[string]*idempotentActivationRecord),
	}
}

// SetDispatcher sets the schedule dispatcher.
func (h *ScheduleHandler) SetDispatcher(dispatcher ScheduleDispatcherInterface) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.dispatcher = dispatcher
}

// SetAuthenticator sets the RBAC authenticator.
func (h *ScheduleHandler) SetAuthenticator(authenticator Authenticator) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.authenticator = authenticator
}

// RegisterRoutes registers the schedules endpoints on a ServeMux according to openapi.yaml.
func (h *ScheduleHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v1/gateways/{gw_id}/schedules/generate", h.handleGenerateSchedule)
	mux.HandleFunc("GET /api/v1/gateways/{gw_id}/schedules/{schedule_id}", h.handleGetSchedule)
	mux.HandleFunc("POST /api/v1/gateways/{gw_id}/schedules/{schedule_id}/review", h.handleReviewSchedule)
	mux.HandleFunc("POST /api/v1/gateways/{gw_id}/schedules/{schedule_id}/activation-requests", h.handleActivationRequest)
}

func (h *ScheduleHandler) checkRole(w http.ResponseWriter, r *http.Request, allowedRoles ...Role) bool {
	h.mu.RLock()
	auth := h.authenticator
	h.mu.RUnlock()

	if auth == nil {
		return true // Unauthenticated mode for simple testing
	}

	authHeader := r.Header.Get("Authorization")
	if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "bearer token required")
		return false
	}

	token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
	if token == "" {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "empty bearer token")
		return false
	}

	role, err := auth.Authenticate(token)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "invalid or expired bearer token")
		return false
	}

	for _, allowed := range allowedRoles {
		if role == allowed {
			return true
		}
	}

	writeError(w, http.StatusForbidden, "FORBIDDEN", fmt.Sprintf("role %s insufficient; requires one of %v", role, allowedRoles))
	return false
}

// handleGenerateSchedule proposes a new versioned TDMA schedule.
// Returns HTTP 202 Accepted. Clients must not infer schedule activation from 202.
// Authority: openapi.yaml, Issue #19, Issue #154, Issue #246.
func (h *ScheduleHandler) handleGenerateSchedule(w http.ResponseWriter, r *http.Request) {
	if !h.checkRole(w, r, RoleAdmin) {
		return
	}

	gwID := r.PathValue("gw_id")
	if err := domain.ValidateGatewayID(gwID); err != nil {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_GATEWAY_ID", "gateway identifier must be 1-32 alphanumeric characters")
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "failed to read request body")
		return
	}

	var req GenerateScheduleRequestDTO
	if err := jsonboundary.DecodeObject(body, maxPayloadBytes, &req); err != nil {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "invalid JSON request: "+err.Error())
		return
	}

	if req.ProfileID != "V2-VN920-STATIC-15N" && req.ProfileID != "P-10S-15" {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_PROFILE_ID", "profile_id must be V2-VN920-STATIC-15N or P-10S-15")
		return
	}

	// 1. Verify Gateway holds an active exclusive channel allocation in Issue #154 database
	allocation, err := h.channelRepo.GetActiveAllocationByGateway(r.Context(), gwID)
	if errors.Is(err, domain.ErrAllocationNotFound) || allocation == nil {
		writeError(w, http.StatusConflict, "GATEWAY_CHANNEL_NOT_ALLOCATED",
			fmt.Sprintf("gateway %s does not hold an active channel allocation; request channel first via /api/v1/gateways/%s/channels/request", gwID, gwID))
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to check channel allocation")
		return
	}

	// 2. Determine schedule version monotonically
	active, err := h.scheduleRepo.GetActiveScheduleByGateway(r.Context(), gwID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to check existing schedule")
		return
	}
	var nextVersion uint32 = 1
	if active != nil {
		nextVersion = active.ScheduleVersion + 1
	}

	// 3. Plan deterministic schedule
	nodes := make([]uint8, 15)
	for i := 0; i < 15; i++ {
		nodes[i] = uint8(i + 1)
	}

	now := time.Now().UTC()
	planReq := scheduler.PlanRequest{
		GatewayID:              gwID,
		NetworkID:              0x00000001,
		ChannelID:              allocation.ChannelID,
		ScheduleVersion:        nextVersion,
		ScheduleGeneration:     uint32(allocation.AllocationGeneration),
		ActiveNodeIDs:          nodes,
		BaseTime:               now,
		ValidityTTL:            24 * time.Hour,
		MinAnnounceSuperframes: 3,
		PHY:                    scheduler.DefaultVN920PHY(),
	}

	result, err := h.planner.Plan(r.Context(), planReq)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "PLANNING_FAILED", err.Error())
		return
	}

	// 4. Save schedule proposal
	if err := h.scheduleRepo.SaveSchedule(r.Context(), result.Schedule); err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to save schedule proposal")
		return
	}

	pendingReview := "PENDING"
	_ = h.scheduleRepo.UpdateReviewState(r.Context(), result.Schedule.ScheduleID, pendingReview, nil)
	_ = h.scheduleRepo.UpdateScheduleState(r.Context(), result.Schedule.ScheduleID, "PROPOSED")

	summary := ScheduleSummaryDTO{
		ScheduleID:              result.Schedule.ScheduleID,
		GatewayID:               result.Schedule.GatewayID,
		Version:                 int64(result.Schedule.ScheduleVersion),
		State:                   "PROPOSED",
		ActivateAtSuperframeSeq: nil,
		CreatedAt:               result.Schedule.CreatedAt.UTC().Format(time.RFC3339),
		ActivatedAt:             nil,
		ReviewState:             &pendingReview,
	}

	writeJSON(w, http.StatusAccepted, summary)
}

// handleGetSchedule retrieves the lifecycle state of a schedule.
func (h *ScheduleHandler) handleGetSchedule(w http.ResponseWriter, r *http.Request) {
	if !h.checkRole(w, r, RoleAdmin, RoleOperator, RoleViewer) {
		return
	}

	gwID := r.PathValue("gw_id")
	schedID := r.PathValue("schedule_id")

	if err := domain.ValidateGatewayID(gwID); err != nil {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_GATEWAY_ID", "invalid gateway identifier")
		return
	}
	if !scheduleIDRegex.MatchString(schedID) {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_SCHEDULE_ID", "schedule_id must be a decimal string")
		return
	}

	sched, err := h.scheduleRepo.GetSchedule(r.Context(), schedID)
	if errors.Is(err, scheduler.ErrScheduleNotFound) || sched == nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", fmt.Sprintf("schedule %s not found", schedID))
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to get schedule")
		return
	}

	if sched.GatewayID != gwID {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "schedule does not belong to specified gateway")
		return
	}

	state, _ := h.scheduleRepo.GetScheduleState(r.Context(), schedID)
	if state == "" {
		state = "PROPOSED"
	}

	active, _ := h.scheduleRepo.GetActiveScheduleByGateway(r.Context(), gwID)
	var activatedAt *string
	var activateSeq *int64
	if active != nil && active.ScheduleID == schedID {
		state = "ACTIVE"
		actStr := active.ActivatedAt.UTC().Format(time.RFC3339)
		activatedAt = &actStr
		seq := int64(active.SuperframeSeq)
		activateSeq = &seq
	}

	revState, rejReason, _ := h.scheduleRepo.GetReviewState(r.Context(), schedID)
	var revPtr *string
	if revState != "" {
		revPtr = &revState
	}

	summary := ScheduleSummaryDTO{
		ScheduleID:              sched.ScheduleID,
		GatewayID:               sched.GatewayID,
		Version:                 int64(sched.ScheduleVersion),
		State:                   state,
		ActivateAtSuperframeSeq: activateSeq,
		CreatedAt:               sched.CreatedAt.UTC().Format(time.RFC3339),
		ActivatedAt:             activatedAt,
		ReviewState:             revPtr,
		RejectReason:            rejReason,
	}

	writeJSON(w, http.StatusOK, summary)
}

// handleReviewSchedule records operator human review decision on a schedule proposal.
func (h *ScheduleHandler) handleReviewSchedule(w http.ResponseWriter, r *http.Request) {
	if !h.checkRole(w, r, RoleAdmin) {
		return
	}

	gwID := r.PathValue("gw_id")
	schedID := r.PathValue("schedule_id")

	sched, err := h.scheduleRepo.GetSchedule(r.Context(), schedID)
	if errors.Is(err, scheduler.ErrScheduleNotFound) || sched == nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", fmt.Sprintf("schedule %s not found", schedID))
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to check schedule")
		return
	}
	if sched.GatewayID != gwID {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "schedule does not belong to specified gateway")
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "failed to read request body")
		return
	}

	var req ScheduleReviewRequestDTO
	if err := jsonboundary.DecodeObject(body, maxPayloadBytes, &req); err != nil {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "invalid review payload: "+err.Error())
		return
	}

	decision := strings.ToUpper(strings.TrimSpace(req.Decision))
	if decision != "APPROVE" && decision != "APPROVED" && decision != "REJECT" && decision != "REJECTED" {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_DECISION", "decision must be APPROVE or REJECT")
		return
	}

	revState := "APPROVED"
	var rejReason *string
	schedState := "PROPOSED"

	if decision == "REJECT" || decision == "REJECTED" {
		revState = "REJECTED"
		schedState = "REJECTED"
		note := strings.TrimSpace(req.Note)
		if note == "" {
			note = strings.TrimSpace(req.Comment)
		}
		if note == "" {
			note = "rejected by operator"
		}
		rejReason = &note
	}

	_ = h.scheduleRepo.UpdateReviewState(r.Context(), schedID, revState, rejReason)
	_ = h.scheduleRepo.UpdateScheduleState(r.Context(), schedID, schedState)

	summary := ScheduleSummaryDTO{
		ScheduleID:              sched.ScheduleID,
		GatewayID:               sched.GatewayID,
		Version:                 int64(sched.ScheduleVersion),
		State:                   schedState,
		ActivateAtSuperframeSeq: nil,
		CreatedAt:               sched.CreatedAt.UTC().Format(time.RFC3339),
		ActivatedAt:             nil,
		ReviewState:             &revState,
		RejectReason:            rejReason,
	}

	writeJSON(w, http.StatusOK, summary)
}

// handleActivationRequest queues an approved schedule proposal for gateway staging over MQTT.
// Returns HTTP 202 Accepted.
// Authority: openapi.yaml, Issue #246, contracts/api/contract-semantics.md §1.1.
func (h *ScheduleHandler) handleActivationRequest(w http.ResponseWriter, r *http.Request) {
	if !h.checkRole(w, r, RoleAdmin) {
		return
	}

	gwID := r.PathValue("gw_id")
	schedID := r.PathValue("schedule_id")

	if err := domain.ValidateGatewayID(gwID); err != nil {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_GATEWAY_ID", "invalid gateway identifier")
		return
	}
	if !scheduleIDRegex.MatchString(schedID) {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_SCHEDULE_ID", "schedule_id must be a decimal string")
		return
	}

	idempotencyKey := strings.TrimSpace(r.Header.Get("X-Idempotency-Key"))
	if idempotencyKey == "" {
		writeError(w, http.StatusUnprocessableEntity, "MISSING_IDEMPOTENCY_KEY", "X-Idempotency-Key header is required")
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "failed to read request body")
		return
	}

	var req ScheduleActivationRequestDTO
	if err := jsonboundary.DecodeObject(body, maxPayloadBytes, &req); err != nil {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "invalid activation request JSON: "+err.Error())
		return
	}
	if req.ExpectedVersion == nil {
		writeError(w, http.StatusUnprocessableEntity, "MISSING_EXPECTED_VERSION", "expected_version is required")
		return
	}

	// 1. Idempotency Key check: if previously accepted with identical payload, return cached response
	idempMapKey := fmt.Sprintf("%s:%s:%s", gwID, schedID, idempotencyKey)
	h.mu.RLock()
	cached, exists := h.idempotencyMap[idempMapKey]
	h.mu.RUnlock()

	if exists {
		if cached.ExpectedVersion == *req.ExpectedVersion {
			writeJSON(w, http.StatusAccepted, cached.Response)
			return
		}
		writeError(w, http.StatusConflict, "IDEMPOTENCY_CONFLICT",
			"request conflicts with previously submitted request for this X-Idempotency-Key")
		return
	}

	// 2. Schedule lookup
	sched, err := h.scheduleRepo.GetSchedule(r.Context(), schedID)
	if errors.Is(err, scheduler.ErrScheduleNotFound) || sched == nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", fmt.Sprintf("schedule %s not found", schedID))
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to check schedule")
		return
	}
	if sched.GatewayID != gwID {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "schedule does not belong to specified gateway")
		return
	}

	// 3. Expected version check
	if *req.ExpectedVersion != sched.ScheduleVersion {
		writeError(w, http.StatusConflict, "VERSION_MISMATCH",
			fmt.Sprintf("expected_version %d does not match schedule version %d", *req.ExpectedVersion, sched.ScheduleVersion))
		return
	}

	// 4. Invariant: review_state must be APPROVED
	revState, _, err := h.scheduleRepo.GetReviewState(r.Context(), schedID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to check schedule review state")
		return
	}
	if revState != "APPROVED" {
		writeError(w, http.StatusConflict, "SCHEDULE_NOT_APPROVED",
			fmt.Sprintf("schedule %s is in review_state %s; only APPROVED schedules can be dispatched for activation", schedID, revState))
		return
	}

	// 5. Invariant: Gateway must hold an active exclusive VN920 channel allocation (Issue #154)
	allocation, err := h.channelRepo.GetActiveAllocationByGateway(r.Context(), gwID)
	if errors.Is(err, domain.ErrAllocationNotFound) || allocation == nil {
		writeError(w, http.StatusConflict, "GATEWAY_CHANNEL_NOT_ALLOCATED",
			fmt.Sprintf("gateway %s does not hold an active channel allocation; activation rejected", gwID))
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to verify gateway channel allocation")
		return
	}

	// 6. Call MQTT dispatcher to stage schedule
	h.mu.RLock()
	disp := h.dispatcher
	h.mu.RUnlock()

	if disp != nil {
		if err := disp.DispatchSchedule(r.Context(), sched); err != nil {
			writeError(w, http.StatusInternalServerError, "DISPATCH_FAILED", "failed to dispatch schedule to gateway: "+err.Error())
			return
		}
	}

	_ = h.scheduleRepo.UpdateScheduleState(r.Context(), schedID, "SENT")

	summary := ScheduleSummaryDTO{
		ScheduleID:              sched.ScheduleID,
		GatewayID:               sched.GatewayID,
		Version:                 int64(sched.ScheduleVersion),
		State:                   "SENT",
		ActivateAtSuperframeSeq: nil,
		CreatedAt:               sched.CreatedAt.UTC().Format(time.RFC3339),
		ActivatedAt:             nil,
		ReviewState:             &revState,
	}

	// Record in idempotency map
	h.mu.Lock()
	h.idempotencyMap[idempMapKey] = &idempotentActivationRecord{
		ExpectedVersion: *req.ExpectedVersion,
		Response:        summary,
	}
	h.mu.Unlock()

	writeJSON(w, http.StatusAccepted, summary)
}
