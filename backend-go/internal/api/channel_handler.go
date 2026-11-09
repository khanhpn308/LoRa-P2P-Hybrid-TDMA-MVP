package api

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

const maxPayloadBytes = 4096

// ErrActiveScheduleOnChannel is returned when a channel change or release is rejected because an active schedule exists.
var ErrActiveScheduleOnChannel = errors.New("cannot change or release channel while gateway holds an active schedule")

// ScheduleGuard defines the interface for checking active schedule constraints before channel operations.
type ScheduleGuard interface {
	CanChangeGatewayChannel(ctx context.Context, gatewayID string) error
}

// ChannelHandler provides HTTP REST endpoints for RF channel catalogue and Gateway allocations.
type ChannelHandler struct {
	repo  storage.ChannelRepository
	guard ScheduleGuard
}

// NewChannelHandler creates a new ChannelHandler, optionally accepting a ScheduleGuard.
func NewChannelHandler(repo storage.ChannelRepository, guard ...ScheduleGuard) *ChannelHandler {
	h := &ChannelHandler{repo: repo}
	if len(guard) > 0 {
		h.guard = guard[0]
	}
	return h
}

// SetScheduleGuard sets the schedule guard for channel operations.
func (h *ChannelHandler) SetScheduleGuard(guard ScheduleGuard) {
	h.guard = guard
}

// RegisterRoutes registers the channel registry API endpoints on a ServeMux according to OpenAPI 3.0.3 spec.
func (h *ChannelHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/channels", h.handleListChannels)
	mux.HandleFunc("POST /api/v1/gateways/{gw_id}/channels/request", h.handleRequestChannel)
	mux.HandleFunc("GET /api/v1/gateways/{gw_id}/channel", h.handleGetChannel)
	mux.HandleFunc("DELETE /api/v1/gateways/{gw_id}/channel", h.handleReleaseChannel)
}

// ChannelInfoDTO matches the ChannelInfo component schema in openapi.yaml.
type ChannelInfoDTO struct {
	ChannelID         string  `json:"channel_id"`
	FrequencyHz       int64   `json:"frequency_hz"`
	BandwidthHz       int64   `json:"bandwidth_hz"`
	Status            string  `json:"status"` // AVAILABLE or ALLOCATED
	AssignedGatewayID *string `json:"assigned_gateway_id,omitempty"`
}

// ChannelRequestDTO matches the ChannelRequest component schema in openapi.yaml.
type ChannelRequestDTO struct {
	ChannelID string `json:"channel_id"`
}

// ChannelAllocationDTO matches the ChannelAllocation component schema in openapi.yaml.
type ChannelAllocationDTO struct {
	GatewayID            string `json:"gateway_id"`
	ChannelID            string `json:"channel_id"`
	FrequencyHz          int64  `json:"frequency_hz"`
	BandwidthHz          int64  `json:"bandwidth_hz"`
	AllocationGeneration int64  `json:"allocation_generation"`
	AllocatedAt          string `json:"allocated_at"`
	RFAuthorized         bool   `json:"rf_authorized"`
	State                string `json:"state"`
}

// ChannelReleaseResponseDTO matches the ChannelReleaseResponse component schema in openapi.yaml.
type ChannelReleaseResponseDTO struct {
	GatewayID  string `json:"gateway_id"`
	ChannelID  string `json:"channel_id"`
	ReleasedAt string `json:"released_at"`
	Status     string `json:"status"`
}

// ErrorResponseDTO provides a clean, sanitized error representation.
type ErrorResponseDTO struct {
	Error   string `json:"error"`
	Message string `json:"message,omitempty"`
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, errCode string, msg string) {
	writeJSON(w, status, ErrorResponseDTO{
		Error:   errCode,
		Message: msg,
	})
}

func toAllocationDTO(alloc *domain.ChannelAllocation) ChannelAllocationDTO {
	freq, _ := domain.GetApprovedFrequencyHz(alloc.ChannelID)
	allocatedAt := alloc.CreatedAt.UTC().Format(time.RFC3339)
	return ChannelAllocationDTO{
		GatewayID:            alloc.GatewayID,
		ChannelID:            alloc.ChannelID,
		FrequencyHz:          freq,
		BandwidthHz:          domain.DefaultBandwidthHz,
		AllocationGeneration: alloc.AllocationGeneration,
		AllocatedAt:          allocatedAt,
		RFAuthorized:         false,
		State:                alloc.Status,
	}
}

// handleListChannels returns all VN920 channels (CH00..CH10) matching OpenAPI /api/v1/channels.
func (h *ChannelHandler) handleListChannels(w http.ResponseWriter, r *http.Request) {
	planVersion := r.URL.Query().Get("plan_version")
	if planVersion == "" {
		planVersion = domain.ChannelPlanVN920V1
	}

	channels, err := h.repo.ListChannels(r.Context(), planVersion)
	if err != nil {
		if errors.Is(err, domain.ErrInvalidChannelPlan) {
			writeError(w, http.StatusBadRequest, "INVALID_CHANNEL_PLAN", "unsupported channel plan version")
			return
		}
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list channels")
		return
	}

	dtos := make([]ChannelInfoDTO, len(channels))
	for i, ch := range channels {
		status := ch.State
		if status == domain.StatusDisabled {
			status = domain.StatusAvailable
		}
		dtos[i] = ChannelInfoDTO{
			ChannelID:   ch.ChannelID,
			FrequencyHz: ch.CenterFrequencyHz,
			BandwidthHz: ch.BandwidthHz,
			Status:      status,
		}
	}

	writeJSON(w, http.StatusOK, dtos)
}

// handleRequestChannel allocates an exclusive channel matching OpenAPI POST /api/v1/gateways/{gw_id}/channels/request.
func (h *ChannelHandler) handleRequestChannel(w http.ResponseWriter, r *http.Request) {
	gwID := strings.TrimSpace(r.PathValue("gw_id"))
	if err := domain.ValidateGatewayID(gwID); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_GATEWAY_ID", "invalid gateway identifier")
		return
	}

	if h.guard != nil {
		if err := h.guard.CanChangeGatewayChannel(r.Context(), gwID); err != nil {
			if errors.Is(err, ErrActiveScheduleOnChannel) {
				writeError(w, http.StatusConflict, "ERR_ACTIVE_SCHEDULE_ON_CHANNEL", "cannot change channel while gateway holds an active schedule")
				return
			}
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to check active schedule guard")
			return
		}
	}

	idempotencyKey := strings.TrimSpace(r.Header.Get("X-Idempotency-Key"))
	if idempotencyKey == "" {
		writeError(w, http.StatusBadRequest, "MISSING_IDEMPOTENCY_KEY", "X-Idempotency-Key header is required")
		return
	}
	if err := domain.ValidateRequestID(idempotencyKey); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_REQUEST_ID", "invalid idempotency key format")
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "failed to read request body")
		return
	}

	var dto ChannelRequestDTO
	if err := jsonboundary.DecodeObject(body, maxPayloadBytes, &dto); err != nil {
		writeError(w, http.StatusBadRequest, "MALFORMED_JSON", err.Error())
		return
	}

	channelID := strings.TrimSpace(dto.ChannelID)
	if err := domain.ValidateChannelID(channelID); err != nil {
		if errors.Is(err, domain.ErrChannelNotFound) {
			writeError(w, http.StatusNotFound, "CHANNEL_NOT_FOUND", "channel not in catalogue")
			return
		}
		writeError(w, http.StatusBadRequest, "INVALID_CHANNEL_ID", "invalid channel identifier")
		return
	}

	req := domain.AllocateRequest{
		GatewayID:          gwID,
		ChannelID:          channelID,
		ChannelPlanVersion: domain.ChannelPlanVN920V1,
		RequestID:          idempotencyKey,
		GrantedBy:          "api",
	}

	alloc, err := h.repo.AllocateChannel(r.Context(), req)
	if err != nil {
		switch {
		case errors.Is(err, domain.ErrChannelInUse):
			writeError(w, http.StatusConflict, "CHANNEL_IN_USE", "channel is currently allocated to another gateway")
		case errors.Is(err, domain.ErrGatewayAlreadyAllocated):
			writeError(w, http.StatusConflict, "GATEWAY_ALREADY_ALLOCATED", "gateway already holds an active channel allocation")
		case errors.Is(err, domain.ErrChannelNotFound):
			writeError(w, http.StatusNotFound, "CHANNEL_NOT_FOUND", "channel not in catalogue")
		case errors.Is(err, domain.ErrChannelDisabled):
			writeError(w, http.StatusBadRequest, "CHANNEL_DISABLED", "channel is administratively disabled")
		case errors.Is(err, domain.ErrInvalidChannelPlan):
			writeError(w, http.StatusBadRequest, "INVALID_CHANNEL_PLAN", "unsupported channel plan version")
		case errors.Is(err, domain.ErrInvalidChannelID):
			writeError(w, http.StatusBadRequest, "INVALID_CHANNEL_ID", "invalid channel identifier")
		case errors.Is(err, domain.ErrInvalidGatewayID):
			writeError(w, http.StatusBadRequest, "INVALID_GATEWAY_ID", "invalid gateway identifier")
		case errors.Is(err, domain.ErrInvalidRequestID):
			writeError(w, http.StatusBadRequest, "INVALID_REQUEST_ID", "invalid request identifier")
		default:
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "allocation failed")
		}
		return
	}

	writeJSON(w, http.StatusCreated, toAllocationDTO(alloc))
}

// handleGetChannel retrieves the current allocation matching OpenAPI GET /api/v1/gateways/{gw_id}/channel.
func (h *ChannelHandler) handleGetChannel(w http.ResponseWriter, r *http.Request) {
	gwID := strings.TrimSpace(r.PathValue("gw_id"))
	if err := domain.ValidateGatewayID(gwID); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_GATEWAY_ID", "invalid gateway identifier")
		return
	}

	alloc, err := h.repo.GetActiveAllocationByGateway(r.Context(), gwID)
	if err != nil {
		if errors.Is(err, domain.ErrAllocationNotFound) {
			writeError(w, http.StatusNotFound, "ALLOCATION_NOT_FOUND", "active allocation not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to get allocation")
		return
	}

	writeJSON(w, http.StatusOK, toAllocationDTO(alloc))
}

// handleReleaseChannel explicitly releases an active allocation matching OpenAPI DELETE /api/v1/gateways/{gw_id}/channel.
func (h *ChannelHandler) handleReleaseChannel(w http.ResponseWriter, r *http.Request) {
	gwID := strings.TrimSpace(r.PathValue("gw_id"))
	if err := domain.ValidateGatewayID(gwID); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_GATEWAY_ID", "invalid gateway identifier")
		return
	}

	if h.guard != nil {
		if err := h.guard.CanChangeGatewayChannel(r.Context(), gwID); err != nil {
			if errors.Is(err, ErrActiveScheduleOnChannel) {
				writeError(w, http.StatusConflict, "ERR_ACTIVE_SCHEDULE_ON_CHANNEL", "cannot release channel while gateway holds an active schedule")
				return
			}
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to check active schedule guard")
			return
		}
	}

	alloc, err := h.repo.GetActiveAllocationByGateway(r.Context(), gwID)
	if err != nil {
		if errors.Is(err, domain.ErrAllocationNotFound) {
			writeError(w, http.StatusNotFound, "ALLOCATION_NOT_FOUND", "active allocation not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to find active allocation")
		return
	}

	req := domain.ReleaseRequest{
		GatewayID:     gwID,
		ChannelID:     alloc.ChannelID,
		RequestID:     "api-release",
		ReleasedBy:    "api",
		ReleaseReason: "operator_released",
	}

	released, err := h.repo.ReleaseChannel(r.Context(), req)
	if err != nil {
		switch {
		case errors.Is(err, domain.ErrAllocationNotFound):
			writeError(w, http.StatusNotFound, "ALLOCATION_NOT_FOUND", "active allocation not found")
		case errors.Is(err, domain.ErrInvalidChannelID):
			writeError(w, http.StatusBadRequest, "INVALID_CHANNEL_ID", "invalid channel identifier")
		case errors.Is(err, domain.ErrInvalidGatewayID):
			writeError(w, http.StatusBadRequest, "INVALID_GATEWAY_ID", "invalid gateway identifier")
		case errors.Is(err, domain.ErrInvalidRequestID):
			writeError(w, http.StatusBadRequest, "INVALID_REQUEST_ID", "invalid request identifier")
		default:
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "release failed")
		}
		return
	}

	relTime := time.Now().UTC()
	if released.ReleasedAt != nil {
		relTime = *released.ReleasedAt
	}

	writeJSON(w, http.StatusOK, ChannelReleaseResponseDTO{
		GatewayID:  released.GatewayID,
		ChannelID:  released.ChannelID,
		ReleasedAt: relTime.UTC().Format(time.RFC3339),
		Status:     released.Status,
	})
}
