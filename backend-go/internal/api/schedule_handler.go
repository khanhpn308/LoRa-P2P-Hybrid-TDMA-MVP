package api

import (
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
}

// ScheduleHandler provides HTTP REST endpoints for schedule planning and review.
type ScheduleHandler struct {
	mu           sync.RWMutex
	scheduleRepo scheduler.ScheduleRepository
	channelRepo  storage.ChannelRepository
	planner      *scheduler.Planner
	reviews      map[string]*reviewRecord
}

type reviewRecord struct {
	ReviewState  string
	RejectReason *string
}

// NewScheduleHandler creates a new ScheduleHandler.
func NewScheduleHandler(
	scheduleRepo scheduler.ScheduleRepository,
	channelRepo storage.ChannelRepository,
	planner *scheduler.Planner,
) *ScheduleHandler {
	return &ScheduleHandler{
		scheduleRepo: scheduleRepo,
		channelRepo:  channelRepo,
		planner:      planner,
		reviews:      make(map[string]*reviewRecord),
	}
}

// RegisterRoutes registers the schedules endpoints on a ServeMux according to openapi.yaml.
func (h *ScheduleHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v1/gateways/{gw_id}/schedules/generate", h.handleGenerateSchedule)
	mux.HandleFunc("GET /api/v1/gateways/{gw_id}/schedules/{schedule_id}", h.handleGetSchedule)
	mux.HandleFunc("POST /api/v1/gateways/{gw_id}/schedules/{schedule_id}/review", h.handleReviewSchedule)
}

// handleGenerateSchedule proposes a new versioned TDMA schedule.
// Returns HTTP 202 Accepted. Clients must not infer schedule activation from 202.
// Authority: openapi.yaml, Issue #19, Issue #154.
func (h *ScheduleHandler) handleGenerateSchedule(w http.ResponseWriter, r *http.Request) {
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
	h.mu.Lock()
	h.reviews[result.Schedule.ScheduleID] = &reviewRecord{
		ReviewState: pendingReview,
	}
	h.mu.Unlock()

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

	state := "PROPOSED"
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

	summary := ScheduleSummaryDTO{
		ScheduleID:              sched.ScheduleID,
		GatewayID:               sched.GatewayID,
		Version:                 int64(sched.ScheduleVersion),
		State:                   state,
		ActivateAtSuperframeSeq: activateSeq,
		CreatedAt:               sched.CreatedAt.UTC().Format(time.RFC3339),
		ActivatedAt:             activatedAt,
	}

	h.mu.RLock()
	if rev, ok := h.reviews[schedID]; ok {
		summary.ReviewState = &rev.ReviewState
		summary.RejectReason = rev.RejectReason
	}
	h.mu.RUnlock()

	writeJSON(w, http.StatusOK, summary)
}

// handleReviewSchedule records operator human review decision on a schedule proposal.
func (h *ScheduleHandler) handleReviewSchedule(w http.ResponseWriter, r *http.Request) {
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
	if decision != "APPROVE" && decision != "REJECT" {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_DECISION", "decision must be APPROVE or REJECT")
		return
	}

	revState := "APPROVED"
	var rejReason *string
	if decision == "REJECT" {
		revState = "REJECTED"
		note := strings.TrimSpace(req.Note)
		if note == "" {
			note = "rejected by operator"
		}
		rejReason = &note
	}

	h.mu.Lock()
	h.reviews[schedID] = &reviewRecord{
		ReviewState:  revState,
		RejectReason: rejReason,
	}
	h.mu.Unlock()

	summary := ScheduleSummaryDTO{
		ScheduleID:              sched.ScheduleID,
		GatewayID:               sched.GatewayID,
		Version:                 int64(sched.ScheduleVersion),
		State:                   "PROPOSED",
		ActivateAtSuperframeSeq: nil,
		CreatedAt:               sched.CreatedAt.UTC().Format(time.RFC3339),
		ActivatedAt:             nil,
		ReviewState:             &revState,
		RejectReason:            rejReason,
	}

	writeJSON(w, http.StatusOK, summary)
}
