package api

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

const maxPayloadBytes = 4096

// ChannelHandler provides HTTP REST endpoints for RF channel catalogue and Gateway allocations.
type ChannelHandler struct {
	repo storage.ChannelRepository
}

// NewChannelHandler creates a new ChannelHandler.
func NewChannelHandler(repo storage.ChannelRepository) *ChannelHandler {
	return &ChannelHandler{repo: repo}
}

// RegisterRoutes registers the channel registry API endpoints on a ServeMux.
func (h *ChannelHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/rf/channels", h.handleListChannels)
	mux.HandleFunc("POST /api/v1/rf/channels/allocate", h.handleAllocateChannel)
	mux.HandleFunc("POST /api/v1/rf/channels/release", h.handleReleaseChannel)
}

// AllocateChannelRequestDTO defines the incoming payload for requesting exclusive channel allocation.
type AllocateChannelRequestDTO struct {
	GatewayID          string `json:"gateway_id"`
	ChannelID          string `json:"channel_id"`
	ChannelPlanVersion string `json:"channel_plan_version"`
	RequestID          string `json:"request_id"`
}

// ReleaseChannelRequestDTO defines the incoming payload for releasing an allocation.
type ReleaseChannelRequestDTO struct {
	GatewayID string `json:"gateway_id"`
	ChannelID string `json:"channel_id"`
	RequestID string `json:"request_id"`
	Reason    string `json:"reason,omitempty"`
}

// ErrorResponseDTO provides a clean, sanitized error representation.
type ErrorResponseDTO struct {
	Error   string `json:"error"`
	Message string `json:"message,omitempty"`
}

// ChannelListResponseDTO contains the channel catalogue list with derived availability.
type ChannelListResponseDTO struct {
	ChannelPlanVersion string               `json:"channel_plan_version"`
	Channels           []domain.ChannelView `json:"channels"`
	RegulatoryNotice   string               `json:"regulatory_notice"`
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

// handleListChannels returns the approved channel catalogue and dynamic availability.
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

	writeJSON(w, http.StatusOK, ChannelListResponseDTO{
		ChannelPlanVersion: planVersion,
		Channels:           channels,
		RegulatoryNotice:   domain.RegulatoryNotice,
	})
}

// handleAllocateChannel allocates an exclusive channel to an authenticated Gateway.
func (h *ChannelHandler) handleAllocateChannel(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "failed to read request body")
		return
	}

	var dto AllocateChannelRequestDTO
	if err := jsonboundary.DecodeObject(body, maxPayloadBytes, &dto); err != nil {
		writeError(w, http.StatusBadRequest, "MALFORMED_JSON", err.Error())
		return
	}

	req := domain.AllocateRequest{
		GatewayID:          strings.TrimSpace(dto.GatewayID),
		ChannelID:          strings.TrimSpace(dto.ChannelID),
		ChannelPlanVersion: strings.TrimSpace(dto.ChannelPlanVersion),
		RequestID:          strings.TrimSpace(dto.RequestID),
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

	writeJSON(w, http.StatusOK, alloc)
}

// handleReleaseChannel explicitly releases an active channel allocation.
func (h *ChannelHandler) handleReleaseChannel(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "failed to read request body")
		return
	}

	var dto ReleaseChannelRequestDTO
	if err := jsonboundary.DecodeObject(body, maxPayloadBytes, &dto); err != nil {
		writeError(w, http.StatusBadRequest, "MALFORMED_JSON", err.Error())
		return
	}

	req := domain.ReleaseRequest{
		GatewayID:     strings.TrimSpace(dto.GatewayID),
		ChannelID:     strings.TrimSpace(dto.ChannelID),
		RequestID:     strings.TrimSpace(dto.RequestID),
		ReleasedBy:    "api",
		ReleaseReason: strings.TrimSpace(dto.Reason),
	}

	alloc, err := h.repo.ReleaseChannel(r.Context(), req)
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

	writeJSON(w, http.StatusOK, alloc)
}
