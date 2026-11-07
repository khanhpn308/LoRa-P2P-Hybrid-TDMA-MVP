package domain

import (
	"errors"
	"strconv"
	"time"
)

var (
	// ErrInvalidAlertFilter indicates one or more filter query parameters violate OpenAPI constraints.
	ErrInvalidAlertFilter = errors.New("invalid alert filter")
)

// AlertTriggerView matches the trigger property in Alert schema.
type AlertTriggerView struct {
	Channel      int `json:"channel"`
	ObservedRaw  int `json:"observed_raw"`
	ThresholdRaw int `json:"threshold_raw"`
}

// AlertView represents an active alert DTO matching the OpenAPI Alert schema.
type AlertView struct {
	AlertID     string            `json:"alert_id"`
	NodeID      uint8             `json:"node_id"`
	GatewayID   string            `json:"gateway_id"`
	EventRef    uint32            `json:"event_ref"`
	EventCode   uint8             `json:"event_code"`
	EventValue  int16             `json:"event_value"`
	Severity    EventSeverity     `json:"severity"`
	TriggeredAt *string           `json:"triggered_at"`
	ReceivedAt  string            `json:"received_at"`
	AckStatus   AckStatus         `json:"ack_status"`
	AckedAt     *string           `json:"acked_at"`
	Trigger     *AlertTriggerView `json:"trigger,omitempty"`
}

// AlertPage matches the OpenAPI AlertPage schema.
type AlertPage struct {
	Items      []AlertView `json:"items"`
	NextCursor *string     `json:"next_cursor"`
}

// AlertFilter defines the query parameters for filtering and cursor-paginating alerts.
type AlertFilter struct {
	Cursor    string
	Limit     int
	Severity  string
	NodeID    *uint8
	GatewayID string
	AckStatus string
}

// Validate validates filter constraints according to OpenAPI specification.
func (f *AlertFilter) Validate() error {
	if f.Limit < 0 || f.Limit > 100 {
		return errors.New("limit must be between 1 and 100")
	}
	if f.Severity != "" {
		switch EventSeverity(f.Severity) {
		case SeverityP0Emergency, SeverityP1High, SeverityP2Medium, SeverityP3Normal:
		default:
			return errors.New("invalid severity enum")
		}
	}
	if f.NodeID != nil && (*f.NodeID < 1 || *f.NodeID > 254) {
		return errors.New("node_id must be between 1 and 254")
	}
	if f.AckStatus != "" {
		switch AckStatus(f.AckStatus) {
		case AckStatusUnacknowledged, AckStatusAcknowledged:
		default:
			return errors.New("invalid ack_status enum")
		}
	}
	return nil
}

// EventToAlertView converts an internal domain Event to an OpenAPI AlertView.
func EventToAlertView(e *Event) AlertView {
	view := AlertView{
		AlertID:    strconv.FormatInt(e.ID, 10),
		NodeID:     e.NodeID,
		GatewayID:  e.GatewayID,
		EventRef:   e.Data.EventRef,
		EventCode:  e.Data.EventCode,
		EventValue: e.Data.EventValue,
		Severity:   e.Severity,
		ReceivedAt: e.IngestedAt.UTC().Format(time.RFC3339),
		AckStatus:  e.AckStatus,
	}
	if e.ObservedAt != nil {
		str := e.ObservedAt.UTC().Format(time.RFC3339)
		view.TriggeredAt = &str
	}
	if e.AcknowledgedAt != nil {
		str := e.AcknowledgedAt.UTC().Format(time.RFC3339)
		view.AckedAt = &str
	}
	if e.Trigger != nil {
		view.Trigger = &AlertTriggerView{
			Channel:      int(e.Trigger.Channel),
			ObservedRaw:  int(e.Trigger.ObservedRaw),
			ThresholdRaw: int(e.Trigger.ThresholdRaw),
		}
	}
	return view
}
