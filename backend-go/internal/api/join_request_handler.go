package api

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strconv"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// DownlinkPublisher publishes downlinks to Gateways via MQTT.
type DownlinkPublisher interface {
	PublishJoinGrant(ctx context.Context, gatewayID string, deviceMAC string, nodeID int) error
}

// JoinRequestHandler provides endpoints for inspecting and approving/rejecting node join requests.
type JoinRequestHandler struct {
	store     storage.JoinRequestStorage
	publisher DownlinkPublisher
}

// NewJoinRequestHandler constructs a new JoinRequestHandler.
func NewJoinRequestHandler(store storage.JoinRequestStorage, publisher DownlinkPublisher) *JoinRequestHandler {
	return &JoinRequestHandler{
		store:     store,
		publisher: publisher,
	}
}

// RegisterRoutes registers the join request routes on a ServeMux.
func (h *JoinRequestHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/devices/requests", h.handleListRequests)
	mux.HandleFunc("POST /api/v1/devices/requests/{id}/approve", h.handleApprove)
	mux.HandleFunc("POST /api/v1/devices/requests/{id}/reject", h.handleReject)
}

func (h *JoinRequestHandler) handleListRequests(w http.ResponseWriter, r *http.Request) {
	list, err := h.store.ListPendingRequests(r.Context())
	if err != nil {
		log.Printf("[JoinRequestHandler] ListPendingRequests error: %v", err)
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list join requests")
		return
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(list)
}

type ApproveRequestDTO struct {
	RequestedNodeID *int `json:"node_id,omitempty"`
}

func (h *JoinRequestHandler) handleApprove(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil || id <= 0 {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "id must be a positive integer")
		return
	}

	var dto ApproveRequestDTO
	if r.Body != nil {
		_ = json.NewDecoder(r.Body).Decode(&dto)
	}

	req, err := h.store.ApproveRequest(r.Context(), id, dto.RequestedNodeID)
	if err != nil {
		if errors.Is(err, storage.ErrRequestNotFound) {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "join request not found")
			return
		}
		if errors.Is(err, storage.ErrNoAvailableNodeID) {
			writeError(w, http.StatusConflict, "CAPACITY_EXCEEDED", "no available node ID remaining (1-254)")
			return
		}
		log.Printf("[JoinRequestHandler] ApproveRequest error: %v", err)
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to approve request")
		return
	}

	// Dispatch downlink to Gateway if publisher configured
	if h.publisher != nil && req.AssignedNodeID != nil {
		if err := h.publisher.PublishJoinGrant(r.Context(), req.GatewayID, req.DeviceMAC, *req.AssignedNodeID); err != nil {
			log.Printf("[JoinRequestHandler] Warning: failed to dispatch MQTT join-grant downlink: %v", err)
		} else {
			log.Printf("[JoinRequestHandler] Dispatched join grant downlink: gw=%s mac=%s node_id=%d", req.GatewayID, req.DeviceMAC, *req.AssignedNodeID)
		}
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(req)
}

func (h *JoinRequestHandler) handleReject(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil || id <= 0 {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "id must be a positive integer")
		return
	}

	if err := h.store.RejectRequest(r.Context(), id); err != nil {
		if errors.Is(err, storage.ErrRequestNotFound) {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "join request not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to reject request")
		return
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "REJECTED",
		"id":     id,
	})
}
