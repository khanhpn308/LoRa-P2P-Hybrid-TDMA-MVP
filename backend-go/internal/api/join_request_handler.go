package api

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strconv"
	"strings"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// DownlinkPublisher publishes downlinks to Gateways.
type DownlinkPublisher interface {
	PublishJoinGrant(ctx context.Context, gatewayID string, deviceMAC string, nodeID int) error
	PublishNodeRevoke(ctx context.Context, gatewayID string, nodeID int) error
	PublishJoinWait(ctx context.Context, gatewayID string, deviceMAC string) error
	PublishJoinReject(ctx context.Context, gatewayID string, deviceMAC string) error
}

// RequestDetailRejecter is an optional interface for storages that return request details on rejection.
type RequestDetailRejecter interface {
	RejectRequestWithDetails(ctx context.Context, id int64) (*domain.DeviceJoinRequest, error)
}

// JoinRequestHandler provides endpoints for inspecting and approving/rejecting node join requests.
type JoinRequestHandler struct {
	store         storage.JoinRequestStorage
	publisher     DownlinkPublisher
	authenticator Authenticator
}

// NewJoinRequestHandler constructs a new JoinRequestHandler with optional Authenticator.
func NewJoinRequestHandler(store storage.JoinRequestStorage, publisher DownlinkPublisher, auth ...Authenticator) *JoinRequestHandler {
	h := &JoinRequestHandler{
		store:     store,
		publisher: publisher,
	}
	if len(auth) > 0 {
		h.authenticator = auth[0]
	}
	return h
}

// RegisterRoutes registers the join request routes on a ServeMux.
func (h *JoinRequestHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/devices/requests", h.handleListRequests)
	mux.HandleFunc("POST /api/v1/devices/requests/{id}/approve", h.handleApprove)
	mux.HandleFunc("POST /api/v1/devices/requests/{id}/reject", h.handleReject)
}

func (h *JoinRequestHandler) checkRBAC(r *http.Request, allowedRoles ...Role) (string, int, error) {
	if claims, ok := auth.ClaimsFromContext(r.Context()); ok && claims != nil {
		for _, allowed := range allowedRoles {
			if Role(claims.Role) == allowed {
				return string(claims.Role), http.StatusOK, nil
			}
		}
		return "", http.StatusForbidden, errors.New("insufficient permissions")
	}

	if h.authenticator == nil {
		return "", http.StatusInternalServerError, errors.New("authenticator unconfigured")
	}
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
		return "", http.StatusUnauthorized, errors.New("bearer token required")
	}
	token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
	if token == "" {
		return "", http.StatusUnauthorized, errors.New("bearer token empty")
	}
	role, err := h.authenticator.Authenticate(token)
	if err != nil {
		return "", http.StatusUnauthorized, errors.New("invalid or expired bearer token")
	}
	for _, allowed := range allowedRoles {
		if role == allowed {
			return string(role), http.StatusOK, nil
		}
	}
	return "", http.StatusForbidden, errors.New("insufficient permissions")
}

func (h *JoinRequestHandler) handleListRequests(w http.ResponseWriter, r *http.Request) {
	// RBAC check: VIEWER, OPERATOR, ADMIN allowed to inspect join requests
	_, status, err := h.checkRBAC(r, RoleViewer, RoleOperator, RoleAdmin)
	if err != nil {
		if status == http.StatusForbidden {
			writeError(w, http.StatusForbidden, "FORBIDDEN", err.Error())
		} else if status == http.StatusInternalServerError {
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		} else {
			writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		}
		return
	}

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
	// RBAC check: OPERATOR or ADMIN required (VIEWER forbidden)
	_, status, err := h.checkRBAC(r, RoleOperator, RoleAdmin)
	if err != nil {
		if status == http.StatusForbidden {
			writeError(w, http.StatusForbidden, "FORBIDDEN", err.Error())
		} else if status == http.StatusInternalServerError {
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		} else {
			writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		}
		return
	}

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
			log.Printf("[JoinRequestHandler] Warning: failed to dispatch join-grant downlink: %v", err)
		} else {
			log.Printf("[JoinRequestHandler] Dispatched join grant downlink: gw=%s mac=%s node_id=%d", req.GatewayID, req.DeviceMAC, *req.AssignedNodeID)
		}
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(req)
}

func (h *JoinRequestHandler) handleReject(w http.ResponseWriter, r *http.Request) {
	// RBAC check: OPERATOR or ADMIN required (VIEWER forbidden)
	_, status, err := h.checkRBAC(r, RoleOperator, RoleAdmin)
	if err != nil {
		if status == http.StatusForbidden {
			writeError(w, http.StatusForbidden, "FORBIDDEN", err.Error())
		} else if status == http.StatusInternalServerError {
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		} else {
			writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		}
		return
	}

	idStr := r.PathValue("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil || id <= 0 {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "id must be a positive integer")
		return
	}

	var req *domain.DeviceJoinRequest
	if detailRejecter, ok := h.store.(RequestDetailRejecter); ok {
		rReq, err := detailRejecter.RejectRequestWithDetails(r.Context(), id)
		if err != nil {
			if errors.Is(err, storage.ErrRequestNotFound) {
				writeError(w, http.StatusNotFound, "NOT_FOUND", "join request not found")
				return
			}
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to reject request")
			return
		}
		req = rReq
	} else {
		if err := h.store.RejectRequest(r.Context(), id); err != nil {
			if errors.Is(err, storage.ErrRequestNotFound) {
				writeError(w, http.StatusNotFound, "NOT_FOUND", "join request not found")
				return
			}
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to reject request")
			return
		}
	}

	// Dispatch downlink to Gateway if publisher configured
	if h.publisher != nil && req != nil {
		if err := h.publisher.PublishJoinReject(r.Context(), req.GatewayID, req.DeviceMAC); err != nil {
			log.Printf("[JoinRequestHandler] Warning: failed to dispatch join-reject downlink: %v", err)
		} else {
			log.Printf("[JoinRequestHandler] Dispatched join reject downlink: gw=%s mac=%s", req.GatewayID, req.DeviceMAC)
		}
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "REJECTED",
		"id":     id,
	})
}
