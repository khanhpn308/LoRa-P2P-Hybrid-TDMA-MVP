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

// NodeRevocationPublisher publishes node revocation downlink messages to Gateways.
type NodeRevocationPublisher interface {
	PublishNodeRevoke(ctx context.Context, gatewayID string, nodeID int) error
}

// MonitoringHandler provides HTTP REST endpoints for gateway status monitoring and paginated node listings.
// Authority: contracts/api/openapi.yaml, contracts/api/contract-semantics.md §1.1.
type MonitoringHandler struct {
	store               storage.StatusStorage
	offlineThreshold    time.Duration
	presenceTracker     *presence.Tracker
	rfTracker           *presence.RFTracker
	authenticator       Authenticator
	revocationPublisher NodeRevocationPublisher
	db                  *sql.DB
}

// SetDB sets an optional database connection handle for lifecycle operations.
func (h *MonitoringHandler) SetDB(db *sql.DB) {
	h.db = db
}

// NewMonitoringHandler constructs a new MonitoringHandler.
// If offlineThreshold <= 0, a default of 5 minutes is applied.
func NewMonitoringHandler(store storage.StatusStorage, offlineThreshold time.Duration, presenceTracker *presence.Tracker, auth ...Authenticator) *MonitoringHandler {
	if offlineThreshold <= 0 {
		offlineThreshold = 5 * time.Minute
	}
	var rfTracker *presence.RFTracker
	if presenceTracker != nil {
		rfTracker = presenceTracker.RF()
	}
	if rfTracker == nil {
		rfTracker = presence.NewRFTracker()
	}
	h := &MonitoringHandler{
		store:            store,
		offlineThreshold: offlineThreshold,
		presenceTracker:  presenceTracker,
		rfTracker:        rfTracker,
	}
	if len(auth) > 0 {
		h.authenticator = auth[0]
	}
	return h
}

// RFTracker returns the active in-memory RF tracker.
func (h *MonitoringHandler) RFTracker() *presence.RFTracker {
	return h.rfTracker
}

// SetRFTracker sets or overrides the active RFTracker.
func (h *MonitoringHandler) SetRFTracker(tracker *presence.RFTracker) {
	h.rfTracker = tracker
}

// SetRevocationPublisher sets the publisher for downlink node revocation commands.
func (h *MonitoringHandler) SetRevocationPublisher(pub NodeRevocationPublisher) {
	h.revocationPublisher = pub
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

		if h.rfTracker != nil {
			if chView := h.rfTracker.GetChannelRFView(gw.GatewayID, -1); chView != nil {
				rssi := chView.ChannelRssiDbm
				gw.ChannelRssiDbm = &rssi
				rfAt := chView.ChannelRfAt
				gw.ChannelRfAt = &rfAt
				ageSec := chView.ChannelRfAgeSeconds
				gw.ChannelRfAgeSeconds = &ageSec
				stale := chView.ChannelRfStale
				gw.ChannelRfStale = &stale
				chIdx := chView.ChannelIdx
				gw.ChannelIdx = &chIdx
				ctxStr := chView.SampleContext
				gw.ChannelSampleContext = &ctxStr
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
	if status, code, msg := h.checkAdminRBAC(r); status != http.StatusOK {
		writeError(w, status, code, msg)
		return
	}

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

	if h.rfTracker != nil {
		if chView := h.rfTracker.GetChannelRFView(gwID, -1); chView != nil {
			rssi := chView.ChannelRssiDbm
			dto.ChannelRssiDbm = &rssi
			rfAt := chView.ChannelRfAt
			dto.ChannelRfAt = &rfAt
			ageSec := chView.ChannelRfAgeSeconds
			dto.ChannelRfAgeSeconds = &ageSec
			stale := chView.ChannelRfStale
			dto.ChannelRfStale = &stale
			chIdx := chView.ChannelIdx
			dto.ChannelIdx = &chIdx
			ctxStr := chView.SampleContext
			dto.ChannelSampleContext = &ctxStr
		}
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

	if h.rfTracker != nil {
		for i := range page.Items {
			var rfView *presence.NodeRFView
			if gwID != "" {
				rfView = h.rfTracker.GetNodeRFView(gwID, page.Items[i].NodeID)
			} else if page.Items[i].GatewayID != "" {
				rfView = h.rfTracker.GetNodeRFView(page.Items[i].GatewayID, page.Items[i].NodeID)
			}
			if rfView == nil {
				rfView = h.rfTracker.GetLatestNodeRFView(page.Items[i].NodeID)
			}
			if rfView != nil {
				rssi := rfView.RssiDbm
				page.Items[i].LastRssiDbm = &rssi
				snr := rfView.SnrDb
				page.Items[i].LastSnrDb = &snr
				rfAt := rfView.LastRfAt
				page.Items[i].LastRfAt = &rfAt
				ageSec := rfView.RfAgeSeconds
				page.Items[i].RfAgeSeconds = &ageSec
				src := rfView.Source
				page.Items[i].RfSource = &src
				stale := rfView.RfStale
				page.Items[i].RfStale = &stale
				page.Items[i].ChannelIdx = rfView.ChannelIdx
			}
		}
	}

	writeJSON(w, http.StatusOK, page)
}

func (h *MonitoringHandler) checkAdminRBAC(r *http.Request) (int, string, string) {
	if claims, ok := auth.ClaimsFromContext(r.Context()); ok && claims != nil {
		if claims.Role != auth.RoleAdmin {
			return http.StatusForbidden, "FORBIDDEN", "role ADMIN required for this operation"
		}
		return http.StatusOK, "", ""
	}

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
	if lifecycle, ok := h.store.(GatewayLifecycleStorage); ok && h.db == nil {
		if err := lifecycle.DeleteGateway(ctx, gwID); err != nil {
			return err
		}
		if h.presenceTracker != nil {
			h.presenceTracker.SetGatewayStatus(gwID, false)
		}
		if h.rfTracker != nil {
			h.rfTracker.RemoveGateway(gwID)
		}
		return nil
	}

	var db *sql.DB
	var shouldClose bool
	if h.db != nil {
		db = h.db
	} else if provider, ok := h.store.(interface{ DB() *sql.DB }); ok && provider.DB() != nil {
		db = provider.DB()
	} else {
		dbURL := os.Getenv("DATABASE_URL")
		if dbURL == "" {
			return errors.New("storage does not support lifecycle operations and DATABASE_URL is not set")
		}
		var err error
		db, err = sql.Open("postgres", dbURL)
		if err != nil {
			return fmt.Errorf("failed to open database connection: %w", err)
		}
		shouldClose = true
	}
	if shouldClose {
		defer db.Close()
	}

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

	if err := tx.Commit(); err != nil {
		return err
	}

	if h.presenceTracker != nil {
		h.presenceTracker.SetGatewayStatus(gwID, false)
	}
	if h.rfTracker != nil {
		h.rfTracker.RemoveGateway(gwID)
	}

	return nil
}

func (h *MonitoringHandler) deleteNode(ctx context.Context, nodeID string) error {
	return h.deleteNodeWithGateway(ctx, nodeID, "")
}

func (h *MonitoringHandler) deleteNodeWithGateway(ctx context.Context, nodeID string, gwIDHint string) error {
	cleanedID := strings.TrimPrefix(strings.TrimSpace(nodeID), "N-")
	numericID, errNum := strconv.Atoi(cleanedID)
	var targetNodeID int
	if errNum == nil && numericID >= 1 && numericID <= 254 {
		targetNodeID = numericID
	}

	hexMAC := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(nodeID), ":", ""))

	gwMap := make(map[string]bool)
	if gwIDHint != "" {
		gwMap[gwIDHint] = true
	}

	if h.store != nil && gwIDHint == "" {
		if page, err := h.store.ListNodes(ctx, domain.NodeFilter{Limit: 250}); err == nil {
			for _, n := range page.Items {
				if (targetNodeID > 0 && n.NodeID == targetNodeID) ||
					(nodeID != "" && (fmt.Sprintf("%d", n.NodeID) == nodeID || fmt.Sprintf("N-%03d", n.NodeID) == nodeID)) {
					if n.GatewayID != "" {
						gwMap[n.GatewayID] = true
					}
				}
			}
		}
	}

	var db *sql.DB
	var shouldClose bool
	if h.db != nil {
		db = h.db
	} else if provider, ok := h.store.(interface{ DB() *sql.DB }); ok && provider.DB() != nil {
		db = provider.DB()
	} else if _, ok := h.store.(GatewayLifecycleStorage); !ok {
		dbURL := os.Getenv("DATABASE_URL")
		if dbURL == "" {
			return errors.New("storage does not support lifecycle operations and DATABASE_URL is not set")
		}
		var err error
		db, err = sql.Open("postgres", dbURL)
		if err != nil {
			return fmt.Errorf("failed to open database connection: %w", err)
		}
		shouldClose = true
	}
	if shouldClose {
		defer db.Close()
	}

	// 1. Resolve targetNodeID from device_mac via device_join_requests if not numeric
	if targetNodeID == 0 && len(hexMAC) == 12 && db != nil {
		rowsReq, err := db.QueryContext(ctx, `SELECT gateway_id, assigned_node_id FROM device_join_requests WHERE LOWER(device_mac) = $1`, hexMAC)
		if err == nil {
			for rowsReq.Next() {
				var gid string
				var nid sql.NullInt64
				if err := rowsReq.Scan(&gid, &nid); err == nil {
					if gid != "" && gwIDHint == "" {
						gwMap[gid] = true
					}
					if nid.Valid && targetNodeID == 0 {
						targetNodeID = int(nid.Int64)
					}
				}
			}
			rowsReq.Close()
		}
	}

	// 2. Discover associated gateways for targetNodeID from DB if available (and no hint specified)
	if targetNodeID > 0 && db != nil && gwIDHint == "" {
		rows, err := db.QueryContext(ctx, `SELECT gateway_id FROM node_health WHERE node_id = $1`, targetNodeID)
		if err == nil {
			for rows.Next() {
				var gid string
				if err := rows.Scan(&gid); err == nil && gid != "" {
					gwMap[gid] = true
				}
			}
			rows.Close()
		}
		rowsReq, err := db.QueryContext(ctx, `SELECT gateway_id FROM device_join_requests WHERE assigned_node_id = $1`, targetNodeID)
		if err == nil {
			for rowsReq.Next() {
				var gid string
				if err := rowsReq.Scan(&gid); err == nil && gid != "" {
					gwMap[gid] = true
				}
			}
			rowsReq.Close()
		}
	}

	if lifecycle, ok := h.store.(GatewayLifecycleStorage); ok && h.db == nil {
		if err := lifecycle.DeleteNode(ctx, nodeID); err != nil {
			return err
		}
	} else if db != nil {
		tx, err := db.BeginTx(ctx, nil)
		if err != nil {
			return fmt.Errorf("failed to begin transaction: %w", err)
		}
		defer tx.Rollback()

		if targetNodeID > 0 {
			// Purge discrete events for the node
			if gwIDHint != "" {
				if _, err := tx.ExecContext(ctx, `DELETE FROM events WHERE node_id = $1 AND gateway_id = $2`, targetNodeID, gwIDHint); err != nil {
					return fmt.Errorf("failed to delete events by node_id and gateway_id: %w", err)
				}
				if _, err := tx.ExecContext(ctx, `DELETE FROM node_health WHERE node_id = $1 AND gateway_id = $2`, targetNodeID, gwIDHint); err != nil {
					return fmt.Errorf("failed to delete node_health by node_id and gateway_id: %w", err)
				}
				if _, err := tx.ExecContext(ctx, `DELETE FROM device_join_requests WHERE assigned_node_id = $1 AND gateway_id = $2`, targetNodeID, gwIDHint); err != nil {
					return fmt.Errorf("failed to delete device_join_requests by assigned_node_id and gateway_id: %w", err)
				}
			} else if len(gwMap) > 0 {
				for gid := range gwMap {
					if _, err := tx.ExecContext(ctx, `DELETE FROM events WHERE node_id = $1 AND gateway_id = $2`, targetNodeID, gid); err != nil {
						return fmt.Errorf("failed to delete events by node_id and gateway_id: %w", err)
					}
					if _, err := tx.ExecContext(ctx, `DELETE FROM node_health WHERE node_id = $1 AND gateway_id = $2`, targetNodeID, gid); err != nil {
						return fmt.Errorf("failed to delete node_health by node_id and gateway_id: %w", err)
					}
					if _, err := tx.ExecContext(ctx, `DELETE FROM device_join_requests WHERE assigned_node_id = $1 AND gateway_id = $2`, targetNodeID, gid); err != nil {
						return fmt.Errorf("failed to delete device_join_requests by assigned_node_id and gateway_id: %w", err)
					}
				}
			} else {
				if _, err := tx.ExecContext(ctx, `DELETE FROM events WHERE node_id = $1`, targetNodeID); err != nil {
					return fmt.Errorf("failed to delete events by node_id: %w", err)
				}
				if _, err := tx.ExecContext(ctx, `DELETE FROM node_health WHERE node_id = $1`, targetNodeID); err != nil {
					return fmt.Errorf("failed to delete node_health by node_id: %w", err)
				}
				if _, err := tx.ExecContext(ctx, `DELETE FROM device_join_requests WHERE assigned_node_id = $1`, targetNodeID); err != nil {
					return fmt.Errorf("failed to delete device_join_requests by assigned_node_id: %w", err)
				}
			}
		}

		if len(hexMAC) == 12 {
			if _, err := tx.ExecContext(ctx, `DELETE FROM device_join_requests WHERE LOWER(device_mac) = $1`, hexMAC); err != nil {
				return fmt.Errorf("failed to delete device_join_requests by mac: %w", err)
			}
			// NOTE: Preserving devices and device_generations tables to keep K_join intact (AC-1/AC-5).
		}

		if err := tx.Commit(); err != nil {
			return err
		}
	}

	if len(gwMap) == 0 && h.store != nil {
		if gws, err := h.store.ListGateways(ctx); err == nil {
			for _, gw := range gws {
				if gw != nil && gw.GatewayID != "" {
					gwMap[gw.GatewayID] = true
				}
			}
		}
	}

	if h.presenceTracker != nil && targetNodeID > 0 {
		h.presenceTracker.SetNodeStatus(targetNodeID, false)
	}
	if h.rfTracker != nil && targetNodeID > 0 {
		h.rfTracker.RemoveNode(targetNodeID)
	}

	if h.revocationPublisher != nil && targetNodeID > 0 {
		for gid := range gwMap {
			if err := h.revocationPublisher.PublishNodeRevoke(ctx, gid, targetNodeID); err != nil {
				log.Printf("[MonitoringHandler] Warning: failed to publish node revoke to gateway %s: %v", gid, err)
			}
		}
	}

	return nil
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

	gwIDHint := strings.TrimSpace(r.URL.Query().Get("gateway_id"))
	if err := h.deleteNodeWithGateway(r.Context(), nodeID, gwIDHint); err != nil {
		log.Printf("[MonitoringHandler] DeleteNode %s error: %v", nodeID, err)
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to delete node")
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"status":  "DELETED",
		"node_id": nodeID,
	})
}
