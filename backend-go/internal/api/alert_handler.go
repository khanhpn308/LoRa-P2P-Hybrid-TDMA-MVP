package api

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var alertIDRegex = regexp.MustCompile(`^(0|[1-9][0-9]{0,19})$`)

// AlertDTO matches the Alert component schema in openapi.yaml.
type AlertDTO struct {
	AlertID     string           `json:"alert_id"`
	NodeID      int              `json:"node_id"`
	GatewayID   string           `json:"gateway_id"`
	EventRef    int64            `json:"event_ref"`
	EventCode   int              `json:"event_code"`
	EventValue  int              `json:"event_value"`
	Severity    string           `json:"severity"`
	TriggeredAt *string          `json:"triggered_at"`
	ReceivedAt  string           `json:"received_at"`
	AckStatus   string           `json:"ack_status"`
	AckedAt     *string          `json:"acked_at"`
	Trigger     *AlertTriggerDTO `json:"trigger,omitempty"`
}

// AlertTriggerDTO matches the trigger property in Alert schema.
type AlertTriggerDTO struct {
	Channel      int `json:"channel"`
	ObservedRaw  int `json:"observed_raw"`
	ThresholdRaw int `json:"threshold_raw"`
}

// AlertPageDTO matches the AlertPage component schema in openapi.yaml.
type AlertPageDTO struct {
	Items      []AlertDTO `json:"items"`
	NextCursor *string    `json:"next_cursor"`
}

// AcknowledgeAlertRequest matches the request payload for POST /api/v1/alerts/{alert_id}/acknowledge.
type AcknowledgeAlertRequest struct {
	AcknowledgedBy *string `json:"acknowledged_by,omitempty"`
}

// AlertHandler provides HTTP REST endpoints for event querying and operator acknowledgment.
type AlertHandler struct {
	repo storage.EventQueryRepository
}

// NewAlertHandler creates a new AlertHandler.
func NewAlertHandler(repo storage.EventQueryRepository) *AlertHandler {
	return &AlertHandler{repo: repo}
}

// RegisterRoutes registers the alerts endpoints on a ServeMux according to openapi.yaml.
func (h *AlertHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/alerts", h.handleListAlerts)
	mux.HandleFunc("POST /api/v1/alerts/{alert_id}/acknowledge", h.handleAcknowledgeAlert)
}

func (h *AlertHandler) handleListAlerts(w http.ResponseWriter, r *http.Request) {
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

	var cursor int64
	if cursorStr := query.Get("cursor"); cursorStr != "" {
		parsed, err := strconv.ParseInt(cursorStr, 10, 64)
		if err != nil || parsed < 0 {
			writeError(w, http.StatusUnprocessableEntity, "INVALID_CURSOR", "cursor must be a non-negative decimal string")
			return
		}
		cursor = parsed
	}

	events, nextCursorID, err := h.repo.ListEvents(r.Context(), cursor, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list alerts")
		return
	}

	items := make([]AlertDTO, 0, len(events))
	for _, e := range events {
		items = append(items, toAlertDTO(e))
	}

	var nextCursor *string
	if nextCursorID > 0 {
		str := strconv.FormatInt(nextCursorID, 10)
		nextCursor = &str
	}

	page := AlertPageDTO{
		Items:      items,
		NextCursor: nextCursor,
	}

	writeJSON(w, http.StatusOK, page)
}

// handleAcknowledgeAlert processes operator acknowledgment in Backend (not an RF ACK down to Node).
// Authority: contracts/api/openapi.yaml, contracts/mqtt/topics.md §9.
func (h *AlertHandler) handleAcknowledgeAlert(w http.ResponseWriter, r *http.Request) {
	alertIDStr := r.PathValue("alert_id")
	if !alertIDRegex.MatchString(alertIDStr) {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_ALERT_ID", "alert_id must be a decimal uint64 string")
		return
	}

	alertID, err := strconv.ParseInt(alertIDStr, 10, 64)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "INVALID_ALERT_ID", "alert_id out of range")
		return
	}

	acknowledgedBy := "operator"
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

	updated, err := h.repo.AcknowledgeEvent(r.Context(), alertID, acknowledgedBy)
	if errors.Is(err, storage.ErrEventNotFound) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", fmt.Sprintf("alert %d not found", alertID))
		return
	}
	if errors.Is(err, storage.ErrAlreadyAcknowledged) {
		writeError(w, http.StatusConflict, "CONFLICT", fmt.Sprintf("alert %d is already acknowledged", alertID))
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to acknowledge alert")
		return
	}

	dto := toAlertDTO(updated)
	writeJSON(w, http.StatusOK, dto)
}

func toAlertDTO(e *domain.Event) AlertDTO {
	dto := AlertDTO{
		AlertID:    strconv.FormatInt(e.ID, 10),
		NodeID:     int(e.NodeID),
		GatewayID:  e.GatewayID,
		EventRef:   int64(e.Data.EventRef),
		EventCode:  int(e.Data.EventCode),
		EventValue: int(e.Data.EventValue),
		Severity:   string(e.Severity),
		ReceivedAt: e.IngestedAt.UTC().Format(time.RFC3339),
		AckStatus:  string(e.AckStatus),
	}

	if e.ObservedAt != nil {
		str := e.ObservedAt.UTC().Format(time.RFC3339)
		dto.TriggeredAt = &str
	}
	if e.AcknowledgedAt != nil {
		str := e.AcknowledgedAt.UTC().Format(time.RFC3339)
		dto.AckedAt = &str
	}
	if e.Trigger != nil {
		dto.Trigger = &AlertTriggerDTO{
			Channel:      int(e.Trigger.Channel),
			ObservedRaw:  int(e.Trigger.ObservedRaw),
			ThresholdRaw: int(e.Trigger.ThresholdRaw),
		}
	}

	return dto
}
