package api

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var (
	alertIDRegex   = regexp.MustCompile(`^(0|[1-9][0-9]{0,19})$`)
	gatewayIDRegex = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)
)

// AlertRepository abstracts persistence operations for alerts.
type AlertRepository interface {
	ListAlerts(ctx context.Context, filter domain.AlertFilter) (*domain.AlertPage, error)
	AcknowledgeAlert(ctx context.Context, alertID int64, acknowledgedBy string) (*domain.AlertView, error)
}

// AcknowledgeAlertRequest matches the request payload for POST /api/v1/alerts/{alert_id}/acknowledge.
type AcknowledgeAlertRequest struct {
	AcknowledgedBy *string `json:"acknowledged_by,omitempty"`
}

// AlertHandler provides HTTP REST endpoints for event querying and operator acknowledgment.
type AlertHandler struct {
	repo          AlertRepository
	authenticator Authenticator
}

// NewAlertHandler creates a new AlertHandler with optional Authenticator.
func NewAlertHandler(repo AlertRepository, auth ...Authenticator) *AlertHandler {
	h := &AlertHandler{repo: repo}
	if len(auth) > 0 {
		h.authenticator = auth[0]
	}
	return h
}

// RegisterRoutes registers the alerts endpoints on a ServeMux according to openapi.yaml.
func (h *AlertHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/alerts", h.handleListAlerts)
	mux.HandleFunc("POST /api/v1/alerts/{alert_id}/acknowledge", h.handleAcknowledgeAlert)
}

func (h *AlertHandler) checkRBAC(r *http.Request, allowedRoles ...Role) (string, int, error) {
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

func (h *AlertHandler) handleListAlerts(w http.ResponseWriter, r *http.Request) {
	// 1. RBAC authorization check (SE-004): VIEWER, OPERATOR, ADMIN
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

	query := r.URL.Query()

	limit := 50
	if limitStr := query.Get("limit"); limitStr != "" {
		parsed, err := strconv.Atoi(limitStr)
		if err != nil || parsed <= 0 || parsed > 100 {
			writeError(w, http.StatusUnprocessableEntity, "INVALID_LIMIT", "limit must be an integer between 1 and 100")
			return
		}
		limit = parsed
	}

	cursor := query.Get("cursor")
	if cursor != "" {
		parsed, err := strconv.ParseInt(cursor, 10, 64)
		if err != nil || parsed < 0 {
			writeError(w, http.StatusUnprocessableEntity, "INVALID_CURSOR", "cursor must be a non-negative decimal string")
			return
		}
	}

	severity := query.Get("severity")
	if severity != "" {
		switch domain.EventSeverity(severity) {
		case domain.SeverityP0Emergency, domain.SeverityP1High, domain.SeverityP2Medium, domain.SeverityP3Normal:
		default:
			writeError(w, http.StatusUnprocessableEntity, "INVALID_SEVERITY", "severity must be one of P0_EMERGENCY, P1_HIGH, P2_MEDIUM, P3_NORMAL")
			return
		}
	}

	var nodeIDPtr *uint8
	if nodeIDStr := query.Get("node_id"); nodeIDStr != "" {
		parsed, err := strconv.ParseUint(nodeIDStr, 10, 8)
		if err != nil || parsed < 1 || parsed > 254 {
			writeError(w, http.StatusUnprocessableEntity, "INVALID_NODE_ID", "node_id must be an integer between 1 and 254")
			return
		}
		nodeID := uint8(parsed)
		nodeIDPtr = &nodeID
	}

	gatewayID := query.Get("gateway_id")
	if gatewayID != "" && !gatewayIDRegex.MatchString(gatewayID) {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_GATEWAY_ID", "gateway_id must be 1-32 alphanumeric characters")
		return
	}

	ackStatus := query.Get("ack_status")
	if ackStatus != "" {
		switch domain.AckStatus(ackStatus) {
		case domain.AckStatusUnacknowledged, domain.AckStatusAcknowledged:
		default:
			writeError(w, http.StatusUnprocessableEntity, "INVALID_ACK_STATUS", "ack_status must be UNACKNOWLEDGED or ACKNOWLEDGED")
			return
		}
	}

	filter := domain.AlertFilter{
		Cursor:    cursor,
		Limit:     limit,
		Severity:  severity,
		NodeID:    nodeIDPtr,
		GatewayID: gatewayID,
		AckStatus: ackStatus,
	}

	page, err := h.repo.ListAlerts(r.Context(), filter)
	if err != nil {
		if errors.Is(err, domain.ErrInvalidAlertFilter) {
			writeError(w, http.StatusUnprocessableEntity, "INVALID_FILTER", err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list alerts")
		return
	}

	writeJSON(w, http.StatusOK, page)
}

// handleAcknowledgeAlert processes operator acknowledgment in Backend (strictly UI workflow, not an RF ACK down to Node).
// Authority: contracts/api/openapi.yaml, contracts/api/contract-semantics.md §1.2.
func (h *AlertHandler) handleAcknowledgeAlert(w http.ResponseWriter, r *http.Request) {
	// 1. RBAC authorization check (SE-004): OPERATOR, ADMIN (VIEWER forbidden)
	actorRole, status, err := h.checkRBAC(r, RoleOperator, RoleAdmin)
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

	alertIDStr := r.PathValue("alert_id")
	if !alertIDRegex.MatchString(alertIDStr) {
		writeError(w, http.StatusBadRequest, "INVALID_ALERT_ID", "alert_id must be a decimal uint64 string")
		return
	}

	alertID, err := strconv.ParseInt(alertIDStr, 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_ALERT_ID", "alert_id out of range")
		return
	}

	acknowledgedBy := actorRole
	if acknowledgedBy == "" {
		acknowledgedBy = "operator"
	}

	if r.ContentLength > 0 {
		body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
		if err != nil {
			writeError(w, http.StatusBadRequest, "BAD_REQUEST", "failed to read request body")
			return
		}
		if len(body) > 0 {
			var req AcknowledgeAlertRequest
			if err := jsonboundary.DecodeObject(body, maxPayloadBytes, &req); err != nil {
				writeError(w, http.StatusBadRequest, "BAD_REQUEST", "invalid JSON request body: "+err.Error())
				return
			}
			if req.AcknowledgedBy != nil && strings.TrimSpace(*req.AcknowledgedBy) != "" {
				acknowledgedBy = strings.TrimSpace(*req.AcknowledgedBy)
			}
		}
	}

	view, err := h.repo.AcknowledgeAlert(r.Context(), alertID, acknowledgedBy)
	if errors.Is(err, storage.ErrAlertNotFound) || errors.Is(err, storage.ErrEventNotFound) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", fmt.Sprintf("alert %d not found", alertID))
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to acknowledge alert")
		return
	}

	writeJSON(w, http.StatusOK, view)
}
