package api

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/presence"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// MonitoringHandler provides HTTP REST endpoints for gateway status monitoring and paginated node listings.
// Authority: contracts/api/openapi.yaml, contracts/api/contract-semantics.md §1.1.
type MonitoringHandler struct {
	store            storage.StatusStorage
	offlineThreshold time.Duration
	presenceTracker  *presence.Tracker
}

// NewMonitoringHandler constructs a new MonitoringHandler.
// If offlineThreshold <= 0, a default of 5 minutes is applied.
func NewMonitoringHandler(store storage.StatusStorage, offlineThreshold time.Duration, presenceTracker *presence.Tracker) *MonitoringHandler {
	if offlineThreshold <= 0 {
		offlineThreshold = 5 * time.Minute
	}
	return &MonitoringHandler{
		store:            store,
		offlineThreshold: offlineThreshold,
		presenceTracker:  presenceTracker,
	}
}

// RegisterRoutes registers the monitoring endpoints on the provided ServeMux.
func (h *MonitoringHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/gateways", h.handleListGateways)
	mux.HandleFunc("POST /api/v1/gateways", h.handleCreateGateway)
	mux.HandleFunc("GET /api/v1/gateways/{gw_id}/status", h.handleGetGatewayStatus)
	mux.HandleFunc("GET /api/v1/nodes", h.handleListNodes)
}

// handleListGateways returns all known gateways with live telemetry and registry metadata.
func (h *MonitoringHandler) handleListGateways(w http.ResponseWriter, r *http.Request) {
	gateways, err := h.store.ListGateways(r.Context())
	if err != nil {
		log.Printf("[MonitoringHandler] ListGateways error: %v", err)
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list gateways")
		return
	}

	now := time.Now().UTC()
	for _, gw := range gateways {
		gw.LastSeenAt = nil
		if h.presenceTracker != nil {
			if h.presenceTracker.IsGatewayOnline(gw.GatewayID) {
				gw.Mode = "ACTIVE"
			} else {
				gw.Mode = "OFFLINE"
			}
		} else if gw.LastSeenAt != nil && h.offlineThreshold > 0 {
			t, parseErr := time.Parse(time.RFC3339, *gw.LastSeenAt)
			if parseErr == nil && now.Sub(t) > h.offlineThreshold {
				gw.Mode = "OFFLINE"
			}
		}
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	if gateways == nil {
		gateways = []*domain.GatewayItem{}
	}
	_ = json.NewEncoder(w).Encode(gateways)
}

type CreateGatewayDTO struct {
	GatewayID string `json:"gateway_id"`
	Name      string `json:"name"`
	Location  string `json:"location"`
	IPAddress string `json:"ip_address"`
}

// handleCreateGateway registers or updates a gateway metadata entry.
func (h *MonitoringHandler) handleCreateGateway(w http.ResponseWriter, r *http.Request) {
	var dto CreateGatewayDTO
	if err := json.NewDecoder(r.Body).Decode(&dto); err != nil {
		writeError(w, http.StatusBadRequest, "MALFORMED_JSON", "invalid JSON payload")
		return
	}

	dto.GatewayID = strings.TrimSpace(dto.GatewayID)
	if !domain.GatewayIDPattern.MatchString(dto.GatewayID) {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_GATEWAY_ID", "gateway_id must match ^[A-Za-z0-9_-]{1,32}$")
		return
	}

	if err := h.store.CreateGateway(r.Context(), dto.GatewayID, dto.Name, dto.Location, dto.IPAddress); err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to register gateway")
		return
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"status":     "CREATED",
		"gateway_id": dto.GatewayID,
	})
}

// handleGetGatewayStatus returns the last-known operational state of a Gateway.
// If in-memory presence tracker is available, it determines ACTIVE vs OFFLINE without disk writes.
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
	if h.presenceTracker != nil {
		if h.presenceTracker.IsGatewayOnline(gwID) {
			mode = string(domain.GatewayModeActive)
		} else {
			mode = string(domain.GatewayModeOffline)
		}
	} else if h.offlineThreshold > 0 && time.Since(rec.LastSeenAt) > h.offlineThreshold {
		mode = string(domain.GatewayModeOffline)
	}

	var lastSeenStr *string
	if h.presenceTracker == nil && !rec.LastSeenAt.IsZero() {
		formatted := rec.LastSeenAt.UTC().Format(time.RFC3339)
		lastSeenStr = &formatted
	}

	dto := domain.GatewayStatusView{
		GatewayID:             rec.GatewayID,
		Mode:                  mode,
		ActiveScheduleVersion: rec.ActiveScheduleVersion,
		LastSeenAt:            lastSeenStr,
		RFDutyPermille:        rec.RFDutyPermille,
		NodeCount:             rec.NodeCount,
	}

	writeJSON(w, http.StatusOK, dto)
}

// handleListNodes returns a cursor-paginated list of nodes matching query filters.
// Ephemeral online status is overlaid from in-memory presence tracker without disk queries.
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
	if h.presenceTracker != nil {
		filter.Status = "" // Overlay in-memory presence
	}

	page, err := h.store.ListNodes(r.Context(), filter)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list nodes")
		return
	}

	if page.Items == nil {
		page.Items = make([]domain.NodeSummary, 0)
	}

	if h.presenceTracker != nil {
		var filtered []domain.NodeSummary
		for i := range page.Items {
			page.Items[i].LastSeenAt = nil
			if h.presenceTracker.IsNodeOnline(page.Items[i].NodeID) {
				page.Items[i].Status = "ONLINE"
			} else {
				page.Items[i].Status = "OFFLINE"
			}

			if statusFilter == "" || page.Items[i].Status == statusFilter {
				filtered = append(filtered, page.Items[i])
			}
		}
		page.Items = filtered
	}

	writeJSON(w, http.StatusOK, page)
}
