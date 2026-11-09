package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
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
	authenticator    Authenticator
}

// NewMonitoringHandler constructs a new MonitoringHandler.
// If offlineThreshold <= 0, a default of 5 minutes is applied.
func NewMonitoringHandler(store storage.StatusStorage, offlineThreshold time.Duration, presenceTracker *presence.Tracker, auth ...Authenticator) *MonitoringHandler {
	if offlineThreshold <= 0 {
		offlineThreshold = 5 * time.Minute
	}
	h := &MonitoringHandler{
		store:            store,
		offlineThreshold: offlineThreshold,
		presenceTracker:  presenceTracker,
	}
	if len(auth) > 0 {
		h.authenticator = auth[0]
	}
	return h
}

// RegisterRoutes registers the monitoring endpoints on the provided ServeMux.
func (h *MonitoringHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/gateways", h.handleListGateways)
	mux.HandleFunc("POST /api/v1/gateways", h.handleCreateGateway)
	mux.HandleFunc("GET /api/v1/gateways/{gw_id}/status", h.handleGetGatewayStatus)
	mux.HandleFunc("DELETE /api/v1/gateways/{gw_id}", h.handleDeleteGateway)
	mux.HandleFunc("GET /api/v1/nodes", h.handleListNodes)
	mux.HandleFunc("DELETE /api/v1/nodes/{node_id}", h.handleDeleteNode)
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

func (h *MonitoringHandler) checkAdminRBAC(r *http.Request) (int, string, string) {
	authenticator := h.authenticator
	if authenticator == nil {
		secret := os.Getenv("JWT_SECRET_KEY")
		if len(secret) < 32 {
			secret = "default-mvp-jwt-secret-key-minimum-32-bytes!!"
		}
		if svc, err := auth.NewJWTService([]byte(secret)); err == nil {
			authenticator = NewJWTAuthenticator(svc)
		}
	}

	authHeader := r.Header.Get("Authorization")
	if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
		return http.StatusUnauthorized, "UNAUTHORIZED", "bearer token required"
	}
	token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
	if token == "" {
		return http.StatusUnauthorized, "UNAUTHORIZED", "bearer token empty"
	}

	if authenticator == nil {
		return http.StatusInternalServerError, "INTERNAL_ERROR", "authenticator unconfigured"
	}

	role, err := authenticator.Authenticate(token)
	if err != nil {
		return http.StatusUnauthorized, "UNAUTHORIZED", "invalid or expired bearer token"
	}

	if role != RoleAdmin {
		return http.StatusForbidden, "FORBIDDEN", "role ADMIN required for this operation"
	}

	return http.StatusOK, "", ""
}

// GatewayLifecycleStorage is an optional interface implemented by storage backends that support lifecycle deletion.
type GatewayLifecycleStorage interface {
	DeleteGateway(ctx context.Context, gatewayID string) error
	DeleteNode(ctx context.Context, nodeID string) error
}

func (h *MonitoringHandler) deleteGateway(ctx context.Context, gwID string) error {
	if lifecycle, ok := h.store.(GatewayLifecycleStorage); ok {
		return lifecycle.DeleteGateway(ctx, gwID)
	}

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		return errors.New("storage does not support lifecycle operations and DATABASE_URL is not set")
	}

	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		return fmt.Errorf("failed to open database connection: %w", err)
	}
	defer db.Close()

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback()

	// 1. Release active RF channel allocation
	if _, err := tx.ExecContext(ctx, `
		UPDATE gateway_channel_allocations
		SET status = 'RELEASED',
		    released_by = 'ADMIN',
		    release_reason = 'Gateway deleted from system registry',
		    released_at = CURRENT_TIMESTAMP,
		    updated_at = CURRENT_TIMESTAMP
		WHERE gateway_id = $1 AND status = 'ALLOCATED'`, gwID); err != nil {
		return fmt.Errorf("failed to release gateway channel allocations: %w", err)
	}

	// 2. Remove from gateway_status
	if _, err := tx.ExecContext(ctx, `DELETE FROM gateway_status WHERE gateway_id = $1`, gwID); err != nil {
		return fmt.Errorf("failed to delete gateway_status: %w", err)
	}

	// 3. Remove from gateways registry
	if _, err := tx.ExecContext(ctx, `DELETE FROM gateways WHERE gateway_id = $1`, gwID); err != nil {
		return fmt.Errorf("failed to delete gateways: %w", err)
	}

	// 4. Remove associated node health entries
	if _, err := tx.ExecContext(ctx, `DELETE FROM node_health WHERE gateway_id = $1`, gwID); err != nil {
		return fmt.Errorf("failed to delete node_health for gateway: %w", err)
	}

	// 5. Remove associated device join requests
	if _, err := tx.ExecContext(ctx, `DELETE FROM device_join_requests WHERE gateway_id = $1`, gwID); err != nil {
		return fmt.Errorf("failed to delete device_join_requests for gateway: %w", err)
	}

	return tx.Commit()
}

func (h *MonitoringHandler) deleteNode(ctx context.Context, nodeID string) error {
	if lifecycle, ok := h.store.(GatewayLifecycleStorage); ok {
		return lifecycle.DeleteNode(ctx, nodeID)
	}

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		return errors.New("storage does not support lifecycle operations and DATABASE_URL is not set")
	}

	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		return fmt.Errorf("failed to open database connection: %w", err)
	}
	defer db.Close()

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback()

	cleanedID := strings.TrimPrefix(strings.TrimSpace(nodeID), "N-")
	if numericID, err := strconv.Atoi(cleanedID); err == nil && numericID >= 1 && numericID <= 254 {
		if _, err := tx.ExecContext(ctx, `DELETE FROM node_health WHERE node_id = $1`, numericID); err != nil {
			return fmt.Errorf("failed to delete node_health by node_id: %w", err)
		}
		if _, err := tx.ExecContext(ctx, `DELETE FROM device_join_requests WHERE assigned_node_id = $1`, numericID); err != nil {
			return fmt.Errorf("failed to delete device_join_requests by assigned_node_id: %w", err)
		}
	}

	hexMAC := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(nodeID), ":", ""))
	if len(hexMAC) == 12 {
		if _, err := tx.ExecContext(ctx, `DELETE FROM device_join_requests WHERE LOWER(device_mac) = $1`, hexMAC); err != nil {
			return fmt.Errorf("failed to delete device_join_requests by mac: %w", err)
		}
		if _, err := tx.ExecContext(ctx, `DELETE FROM devices WHERE encode(device_mac, 'hex') = $1`, hexMAC); err != nil {
			return fmt.Errorf("failed to delete devices by mac: %w", err)
		}
	}

	return tx.Commit()
}

// handleDeleteGateway handles DELETE /api/v1/gateways/{gw_id}.
func (h *MonitoringHandler) handleDeleteGateway(w http.ResponseWriter, r *http.Request) {
	if status, code, msg := h.checkAdminRBAC(r); status != http.StatusOK {
		writeError(w, status, code, msg)
		return
	}

	gwID := strings.TrimSpace(r.PathValue("gw_id"))
	if !domain.GatewayIDPattern.MatchString(gwID) {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_GATEWAY_ID", "gateway_id must match ^[A-Za-z0-9_-]{1,32}$")
		return
	}

	if err := h.deleteGateway(r.Context(), gwID); err != nil {
		log.Printf("[MonitoringHandler] DeleteGateway %s error: %v", gwID, err)
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to delete gateway")
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"status":     "DELETED",
		"gateway_id": gwID,
	})
}

// handleDeleteNode handles DELETE /api/v1/nodes/{node_id}.
func (h *MonitoringHandler) handleDeleteNode(w http.ResponseWriter, r *http.Request) {
	if status, code, msg := h.checkAdminRBAC(r); status != http.StatusOK {
		writeError(w, status, code, msg)
		return
	}

	nodeID := strings.TrimSpace(r.PathValue("node_id"))
	if nodeID == "" {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_NODE_ID", "node_id required")
		return
	}

	if err := h.deleteNode(r.Context(), nodeID); err != nil {
		log.Printf("[MonitoringHandler] DeleteNode %s error: %v", nodeID, err)
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to delete node")
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"status":  "DELETED",
		"node_id": nodeID,
	})
}
