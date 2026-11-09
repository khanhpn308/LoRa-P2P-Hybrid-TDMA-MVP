package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// NodeSummaryDTO matches the NodeSummary component schema in openapi.yaml.
type NodeSummaryDTO struct {
	NodeID         int     `json:"node_id"`
	GatewayID      string  `json:"gateway_id"`
	Name           *string `json:"name,omitempty"`
	AssignedSlotID *int    `json:"assigned_slot_id"`
	LastSeenAt     string  `json:"last_seen_at"`
	Status         string  `json:"status"`
}

// NodePageDTO matches the NodePage component schema in openapi.yaml.
type NodePageDTO struct {
	Items      []NodeSummaryDTO `json:"items"`
	NextCursor *string          `json:"next_cursor"`
}

// DeprecatedTelemetryResponseDTO matches the 410 Gone payload for legacy telemetry queries.
type DeprecatedTelemetryResponseDTO struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// NodeHandler provides HTTP REST endpoints for nodes health and legacy telemetry rejection.
type NodeHandler struct {
	repo storage.EventQueryRepository
}

// NewNodeHandler creates a new NodeHandler.
func NewNodeHandler(repo storage.EventQueryRepository) *NodeHandler {
	return &NodeHandler{repo: repo}
}

// RegisterRoutes registers the node endpoints on a ServeMux according to openapi.yaml.
// Note: GET /api/v1/nodes is registered by MonitoringHandler to provide full status,
// presence tracking, and cursor pagination without route collision.
func (h *NodeHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/nodes/{node_id}/telemetry", h.handleGetNodeTelemetry)
}

// RegisterListNodesRoute registers the node listing route on a ServeMux.
// In production BuildServeMux, GET /api/v1/nodes is registered by MonitoringHandler.
func (h *NodeHandler) RegisterListNodesRoute(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/nodes", h.handleListNodes)
}

// handleListNodes returns confirmed node health reports derived from UP_HEALTH_REPLY (0x44 21B).
// Authority: openapi.yaml, Issue #18, Issue #128.
func (h *NodeHandler) handleListNodes(w http.ResponseWriter, r *http.Request) {
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

	gatewayID := query.Get("gateway_id")
	nodes, err := h.repo.ListNodeHealth(r.Context(), gatewayID, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list nodes")
		return
	}

	items := make([]NodeSummaryDTO, 0, len(nodes))
	for _, n := range nodes {
		slotID := int(n.NodeID)
		items = append(items, NodeSummaryDTO{
			NodeID:         int(n.NodeID),
			GatewayID:      n.GatewayID,
			AssignedSlotID: &slotID,
			LastSeenAt:     n.LastSeenAt.UTC().Format(time.RFC3339),
			Status:         string(n.HealthStatus),
		})
	}

	page := NodePageDTO{
		Items:      items,
		NextCursor: nil,
	}

	writeJSON(w, http.StatusOK, page)
}

// handleGetNodeTelemetry returns HTTP 410 Gone.
// Periodic application telemetry and SET_PERIODIC_MODE cease as current business flows.
// Authority: Issue #125, Issue #128, Issue #303, openapi.yaml.
func (h *NodeHandler) handleGetNodeTelemetry(w http.ResponseWriter, r *http.Request) {
	nodeIDStr := r.PathValue("node_id")
	nodeID, err := strconv.Atoi(nodeIDStr)
	if err != nil || nodeID < 1 || nodeID > 254 {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_NODE_ID", "node_id must be between 1 and 254")
		return
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusGone)
	_ = json.NewEncoder(w).Encode(DeprecatedTelemetryResponseDTO{
		Code:    "TELEMETRY_PERIODIC_MODE_DEPRECATED",
		Message: "Periodic application telemetry and SET_PERIODIC_MODE cease as current business flows. Event-Only V2 alerts arrive via ALERT_TRIGGERED.",
	})
}
