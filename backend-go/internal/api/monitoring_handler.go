package api

import (
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// MonitoringHandler provides HTTP REST endpoints for gateway status monitoring and paginated node listings.
// Authority: contracts/api/openapi.yaml, contracts/api/contract-semantics.md §1.1.
type MonitoringHandler struct {
	store            storage.StatusStorage
	offlineThreshold time.Duration
}

// NewMonitoringHandler constructs a new MonitoringHandler.
// If offlineThreshold <= 0, a default of 5 minutes is applied.
func NewMonitoringHandler(store storage.StatusStorage, offlineThreshold time.Duration) *MonitoringHandler {
	if offlineThreshold <= 0 {
		offlineThreshold = 5 * time.Minute
	}
	return &MonitoringHandler{
		store:            store,
		offlineThreshold: offlineThreshold,
	}
}

// RegisterRoutes registers the monitoring endpoints on the provided ServeMux.
func (h *MonitoringHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/gateways/{gw_id}/status", h.handleGetGatewayStatus)
	mux.HandleFunc("GET /api/v1/nodes", h.handleListNodes)
}

// handleGetGatewayStatus returns the last-known operational state of a Gateway.
// If last_seen_at exceeds offlineThreshold, mode is marked as OFFLINE.
// Returns HTTP 404 if the gateway has never reported status.
// Authority: openapi.yaml, contract-semantics.md.
func (h *MonitoringHandler) handleGetGatewayStatus(w http.ResponseWriter, r *http.Request) {
	gwID := r.PathValue("gw_id")
	if !domain.GatewayIDPattern.MatchString(gwID) {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_GATEWAY_ID", "gateway_id must match ^[A-Za-z0-9_-]{1,32}$")
		return
	}

	rec, err := h.store.GetGatewayStatus(r.Context(), gwID)
	if errors.Is(err, storage.ErrGatewayStatusNotFound) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "gateway status not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to retrieve gateway status")
		return
	}

	mode := string(rec.Mode)
	if h.offlineThreshold > 0 && time.Since(rec.LastSeenAt) > h.offlineThreshold {
		mode = string(domain.GatewayModeOffline)
	}

	lastSeenStr := rec.LastSeenAt.UTC().Format(time.RFC3339)
	dto := domain.GatewayStatusView{
		GatewayID:             rec.GatewayID,
		Mode:                  mode,
		ActiveScheduleVersion: rec.ActiveScheduleVersion,
		LastSeenAt:            &lastSeenStr,
		RFDutyPermille:        rec.RFDutyPermille,
		NodeCount:             rec.NodeCount,
	}

	writeJSON(w, http.StatusOK, dto)
}

// handleListNodes returns a cursor-paginated list of nodes matching query filters.
// Authority: openapi.yaml, contract-semantics.md.
func (h *MonitoringHandler) handleListNodes(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()

	limit := 50
	if limitStr := query.Get("limit"); limitStr != "" {
		parsed, err := strconv.Atoi(limitStr)
		if err != nil || parsed <= 0 || parsed > 100 {
			writeError(w, http.StatusUnprocessableEntity, "INVALID_LIMIT", "limit must be between 1 and 100")
			return
		}
		limit = parsed
	}

	gwID := query.Get("gateway_id")
	if gwID != "" && !domain.GatewayIDPattern.MatchString(gwID) {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_GATEWAY_ID", "gateway_id must match ^[A-Za-z0-9_-]{1,32}$")
		return
	}

	statusFilter := query.Get("status")
	if statusFilter != "" {
		switch statusFilter {
		case "ONLINE", "OFFLINE", "UNSYNCED", "UNKNOWN":
		default:
			writeError(w, http.StatusUnprocessableEntity, "INVALID_STATUS", "status must be ONLINE, OFFLINE, UNSYNCED, or UNKNOWN")
			return
		}
	}

	cursor := query.Get("cursor")
	if cursor != "" {
		parsedCursor, err := strconv.Atoi(cursor)
		if err != nil || parsedCursor < 0 {
			writeError(w, http.StatusUnprocessableEntity, "INVALID_CURSOR", "cursor must be a non-negative decimal string")
			return
		}
	}

	filter := domain.NodeFilter{
		GatewayID: gwID,
		Status:    statusFilter,
		Cursor:    cursor,
		Limit:     limit,
	}

	page, err := h.store.ListNodes(r.Context(), filter)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list nodes")
		return
	}

	if page.Items == nil {
		page.Items = make([]domain.NodeSummary, 0)
	}

	writeJSON(w, http.StatusOK, page)
}
