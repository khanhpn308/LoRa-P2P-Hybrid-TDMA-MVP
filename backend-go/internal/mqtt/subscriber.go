package mqtt

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	paho "github.com/eclipse/paho.mqtt.golang"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/presence"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var (
	statusTopicPattern    = regexp.MustCompile(`^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/status$`)
	alertTopicPattern     = regexp.MustCompile(`^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/alert$`)
	joinTopicPattern      = regexp.MustCompile(`^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/join-(hello|request)$`)
	heartbeatTopicPattern = regexp.MustCompile(`^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/heartbeat$`)
	rfMetricsTopicPattern = regexp.MustCompile(`^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/rf-metrics$`)
)

// RFMetricsPayload parses both single-sample and batched RF metrics envelopes from Gateways.
type RFMetricsPayload struct {
	SchemaVersion     string            `json:"schema_version"`
	GatewayID         string            `json:"gateway_id"`
	GatewayEpoch      string            `json:"gateway_epoch"`
	SampleSeq         string            `json:"sample_seq"`
	SampleMonotonicUS string            `json:"sample_monotonic_us"`
	AgeMs             *uint32           `json:"age_ms"`
	Kind              string            `json:"kind"`
	ChannelIdx        *int              `json:"channel_idx"`
	NodeID            *int              `json:"node_id"`
	RssiDbm           *int              `json:"rssi_dbm"`
	SnrDb             *float64          `json:"snr_db"`
	Source            string            `json:"source"`
	Validation        string            `json:"validation"`
	ChannelRssiDbm    *int              `json:"channel_rssi_dbm"`
	SampleContext     string            `json:"sample_context"`
	Samples           []RFMetricsSample `json:"samples"`
}

// RFMetricsSample represents a single RF observation within a batched payload.
type RFMetricsSample struct {
	SampleSeq         string   `json:"sample_seq"`
	SampleMonotonicUS string   `json:"sample_monotonic_us"`
	AgeMs             *uint32  `json:"age_ms"`
	Kind              string   `json:"kind"`
	ChannelIdx        *int     `json:"channel_idx"`
	NodeID            *int     `json:"node_id"`
	RssiDbm           *int     `json:"rssi_dbm"`
	SnrDb             *float64 `json:"snr_db"`
	Source            string   `json:"source"`
	Validation        string   `json:"validation"`
	ChannelRssiDbm    *int     `json:"channel_rssi_dbm"`
	SampleContext     string   `json:"sample_context"`
}

// LiveStatusPayload parses both lightweight birth/LWT messages and detailed status snapshots.
type LiveStatusPayload struct {
	GatewayID             string `json:"gateway_id"`
	Status                string `json:"status"` // "online" or "offline"
	Mode                  string `json:"mode"`   // "ACTIVE", "BOOTSTRAP", etc.
	ActiveScheduleVersion uint32 `json:"active_schedule_version"`
	ChannelID             string `json:"channel_id"`
	RFDutyPermille        int    `json:"rf_duty_permille"`
	NodeCount             int    `json:"node_count"`
	FreeHeapBytes         uint32 `json:"free_heap_bytes"`
}

// JoinRelayPayload represents incoming node join requests from Gateway over MQTT.
type JoinRelayPayload struct {
	GatewayID   string  `json:"gateway_id"`
	DeviceMAC   string  `json:"device_mac"`
	RSSI        int     `json:"rssi"`
	SNR         float64 `json:"snr"`
	RawFrameHex string  `json:"raw_frame_hex"`
}

// RealtimeBroadcaster broadcasts realtime events to clients.
type RealtimeBroadcaster interface {
	BroadcastEnvelope(ctx context.Context, env *realtime.RealtimeEnvelope) error
	BroadcastGatewayStatus(ctx context.Context, payload realtime.GatewayStatusChangedPayload) error
	BroadcastAlert(ctx context.Context, payload realtime.AlertTriggeredPayload) error
}

// GatewayStatusSubscriber subscribes to MQTT gateway status, node alerts, and join requests.
type GatewayStatusSubscriber struct {
	client          paho.Client
	store           storage.StatusStorage
	eventStore      storage.EventRepository
	joinReqStore    storage.JoinRequestStorage
	presenceTracker *presence.Tracker
	rfTracker       *presence.RFTracker
	hub             RealtimeBroadcaster
	brokerURI       string
	mu              sync.Mutex
	stopTicker      chan struct{}
}

// NewGatewayStatusSubscriber creates a new subscriber for operational monitoring.
func NewGatewayStatusSubscriber(
	brokerURI string,
	store storage.StatusStorage,
	hub *realtime.Hub,
	eventStore storage.EventRepository,
	joinReqStore storage.JoinRequestStorage,
	presenceTracker *presence.Tracker,
) *GatewayStatusSubscriber {
	if presenceTracker == nil {
		presenceTracker = presence.NewTracker()
	}
	rfTracker := presenceTracker.RF()
	if rfTracker == nil {
		rfTracker = presence.NewRFTracker()
	}
	var broadcaster RealtimeBroadcaster
	if hub != nil {
		broadcaster = hub
	}
	return &GatewayStatusSubscriber{
		brokerURI:       brokerURI,
		store:           store,
		eventStore:      eventStore,
		joinReqStore:    joinReqStore,
		presenceTracker: presenceTracker,
		rfTracker:       rfTracker,
		hub:             broadcaster,
		stopTicker:      make(chan struct{}),
	}
}

// RFTracker returns the active RFTracker instance.
func (s *GatewayStatusSubscriber) RFTracker() *presence.RFTracker {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.rfTracker
}

// SetRFTracker overrides or sets the RFTracker instance.
func (s *GatewayStatusSubscriber) SetRFTracker(tracker *presence.RFTracker) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.rfTracker = tracker
}

// Start begins listening to MQTT publications asynchronously with an automatic background retry loop.
func (s *GatewayStatusSubscriber) Start(ctx context.Context) error {
	opts := paho.NewClientOptions()
	opts.AddBroker(s.brokerURI)
	opts.SetClientID(fmt.Sprintf("backend-sub-%d", time.Now().UnixNano()%100000))
	opts.SetAutoReconnect(true)
	opts.SetKeepAlive(30 * time.Second)

	opts.SetOnConnectHandler(func(c paho.Client) {
		log.Printf("[MQTT Subscriber] Connected to broker %s; registering subscriptions...", s.brokerURI)
		// 1. Gateway Status
		c.Subscribe("iot/v1/gw/+/uplink/status", 1, s.handleMessage)
		// 2. Node Events / Alerts
		c.Subscribe("iot/v1/gw/+/uplink/alert", 1, s.handleAlertMessage)
		// 3. Node Join Requests
		c.Subscribe("iot/v1/gw/+/uplink/join-hello", 1, s.handleJoinMessage)
		c.Subscribe("iot/v1/gw/+/uplink/join-request", 1, s.handleJoinMessage)
		// 4. Binary Heartbeat & Node Liveness Bitmap
		c.Subscribe("iot/v1/gw/+/uplink/heartbeat", 1, s.handleHeartbeatMessage)
		// 5. LoRa RF Metrics (Issue #392 / #393)
		c.Subscribe("iot/v1/gw/+/uplink/rf-metrics", 1, s.handleRFMetricsMessage)
	})

	opts.SetConnectionLostHandler(func(c paho.Client, err error) {
		log.Printf("[MQTT Subscriber] Broker connection lost: %v", err)
	})

	client := paho.NewClient(opts)
	s.client = client

	token := client.Connect()
	if token.Wait() && token.Error() != nil {
		log.Printf("[MQTT Subscriber] Initial connect error: %v (retrying in background...)", token.Error())
		go func() {
			for {
				select {
				case <-s.stopTicker:
					return
				case <-time.After(3 * time.Second):
					if !s.client.IsConnected() {
						t := s.client.Connect()
						if t.Wait() && t.Error() == nil {
							log.Printf("[MQTT Subscriber] Background connection succeeded to %s", s.brokerURI)
							return
						}
					}
				}
			}
		}()
	}

	// Background Watchdog: check for gateway heartbeat timeouts every 10s (60s threshold)
	go func() {
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-s.stopTicker:
				return
			case <-ticker.C:
				if s.presenceTracker != nil {
					timedOut := s.presenceTracker.CheckGatewayTimeouts(60 * time.Second)
					for _, gwID := range timedOut {
						log.Printf("[Heartbeat Watchdog] Gateway %s heartbeat timed out (>60s), marked OFFLINE", gwID)
						if s.hub != nil {
							_ = s.hub.BroadcastGatewayStatus(context.Background(), realtime.GatewayStatusChangedPayload{
								GatewayID:  gwID,
								Mode:       string(domain.GatewayModeOffline),
								LastSeenAt: nil,
							})
						}
					}
				}
			}
		}
	}()

	return nil
}

// handleHeartbeatMessage processes Type 1 (Gateway Heartbeat) and Type 2 (Node Liveness Bitmap).
func (s *GatewayStatusSubscriber) handleHeartbeatMessage(client paho.Client, msg paho.Message) {
	topic := msg.Topic()
	payload := msg.Payload()
	matches := heartbeatTopicPattern.FindStringSubmatch(topic)
	if len(matches) < 2 || len(payload) < 2 {
		return
	}
	gwID := matches[1]

	msgType := payload[0]
	switch msgType {
	case 0x01: // Type 1: Gateway Liveness Heartbeat (16 bytes)
		if len(payload) >= 16 {
			flags := payload[1]
			wifiRSSI := int8(payload[2])
			uptimeS := binary.LittleEndian.Uint32(payload[4:8])
			freeHeap := binary.LittleEndian.Uint32(payload[8:12])
			rxEvents := binary.LittleEndian.Uint32(payload[12:16])

			wasOnline := s.presenceTracker != nil && s.presenceTracker.IsGatewayOnline(gwID)
			if s.presenceTracker != nil {
				s.presenceTracker.UpdateGatewayHeartbeat(gwID, flags, wifiRSSI, uptimeS, freeHeap, rxEvents)
			}

			if !wasOnline && s.hub != nil {
				log.Printf("[MQTT Subscriber] Gateway %s is now ACTIVE via binary heartbeat (rssi=%d uptime=%ds heap=%dB)", gwID, wifiRSSI, uptimeS, freeHeap)
				_ = s.hub.BroadcastGatewayStatus(context.Background(), realtime.GatewayStatusChangedPayload{
					GatewayID:  gwID,
					Mode:       string(domain.GatewayModeActive),
					LastSeenAt: nil,
				})
			}
		}
	case 0x02: // Type 2: Node Liveness Bitmap
		nodeCount := int(payload[1])
		bitmapLen := (nodeCount + 7) / 8
		if len(payload) >= 2+bitmapLen {
			bitmapBytes := payload[2 : 2+bitmapLen]
			if s.presenceTracker != nil {
				s.presenceTracker.ApplyNodeBitmap(gwID, nodeCount, bitmapBytes)
			}
			log.Printf("[MQTT Subscriber] Gateway %s applied Node Liveness Bitmap: N=%d, bytes=%x", gwID, nodeCount, bitmapBytes)
		}
	default:
		log.Printf("[MQTT Subscriber] Unknown heartbeat packet type 0x%02X from %s", msgType, gwID)
	}
}

func (s *GatewayStatusSubscriber) handleMessage(client paho.Client, msg paho.Message) {
	topic := msg.Topic()
	payload := msg.Payload()
	log.Printf("[MQTT Subscriber] Received status on %s: %s", topic, string(payload))

	matches := statusTopicPattern.FindStringSubmatch(topic)
	if len(matches) < 2 {
		return
	}
	gwID := matches[1]

	var wire LiveStatusPayload
	if err := json.Unmarshal(payload, &wire); err != nil {
		log.Printf("[MQTT Subscriber] Failed to decode status payload for %s: %v", gwID, err)
		return
	}

	if wire.GatewayID == "" {
		wire.GatewayID = gwID
	}

	mode := domain.GatewayModeActive
	if strings.ToLower(wire.Status) == "offline" || strings.ToUpper(wire.Mode) == "OFFLINE" {
		mode = domain.GatewayModeOffline
	}

	// Update ephemeral presence in RAM (0 disk writes)
	if s.presenceTracker != nil {
		s.presenceTracker.SetGatewayStatus(wire.GatewayID, mode == domain.GatewayModeActive)
	}

	log.Printf("[MQTT Subscriber] Gateway %s in-memory presence is now %s", wire.GatewayID, mode)

	// Broadcast via WebSocket to connected clients
	if s.hub != nil {
		_ = s.hub.BroadcastGatewayStatus(context.Background(), realtime.GatewayStatusChangedPayload{
			GatewayID:  wire.GatewayID,
			Mode:       string(mode),
			LastSeenAt: nil,
		})
	}
}

// handleAlertMessage processes UP_EVENT publications from Gateways.
func (s *GatewayStatusSubscriber) handleAlertMessage(client paho.Client, msg paho.Message) {
	topic := msg.Topic()
	payload := msg.Payload()
	log.Printf("[MQTT Subscriber] Received alert on %s: %s", topic, string(payload))

	matches := alertTopicPattern.FindStringSubmatch(topic)
	if len(matches) < 2 {
		return
	}
	gwID := matches[1]

	var wire map[string]interface{}
	if err := json.Unmarshal(payload, &wire); err != nil {
		log.Printf("[MQTT Subscriber] Malformed alert payload: %v", err)
		return
	}

	nodeID := 0
	if nVal, ok := wire["node_id"]; ok {
		switch v := nVal.(type) {
		case float64:
			nodeID = int(v)
		case string:
			nodeID, _ = strconv.Atoi(v)
		}
	}
	if nodeID <= 0 || nodeID > 254 {
		log.Printf("[MQTT Subscriber] Alert with invalid node_id: %v", wire["node_id"])
		return
	}

	now := time.Now().UTC()
	seqStr := fmt.Sprintf("%d", now.UnixNano())
	if es, ok := wire["event_seq"].(string); ok && es != "" {
		seqStr = es
	}
	epochStr := "00000000-0000-0000-0000-000000000001"
	if ep, ok := wire["gateway_epoch"].(string); ok && ep != "" {
		epochStr = ep
	}
	eventID := fmt.Sprintf("%s:%s:%s", gwID, epochStr, seqStr)

	eventCode := uint8(1)
	eventValue := int16(0)
	if dataMap, ok := wire["data"].(map[string]interface{}); ok {
		if c, ok := dataMap["event_code"].(float64); ok {
			eventCode = uint8(c)
		}
		if val, ok := dataMap["event_value"].(float64); ok {
			eventValue = int16(val)
		}
	} else {
		if c, ok := wire["event_code"].(float64); ok {
			eventCode = uint8(c)
		}
		if val, ok := wire["event_value"].(float64); ok {
			eventValue = int16(val)
		}
	}

	severity := domain.SeverityP3Normal
	if sev, ok := wire["severity"].(string); ok && sev != "" {
		switch strings.ToUpper(sev) {
		case "P0_EMERGENCY", "EMERGENCY", "CRITICAL":
			severity = domain.SeverityP0Emergency
		case "P1_HIGH", "HIGH":
			severity = domain.SeverityP1High
		case "P2_MEDIUM", "MEDIUM", "WARNING", "WARN":
			severity = domain.SeverityP2Medium
		default:
			severity = domain.SeverityP3Normal
		}
	}

	observedAt := now
	shaBytes := sha256.Sum256(payload)
	var rawHash [32]byte
	copy(rawHash[:], shaBytes[:])

	evt := &domain.Event{
		EventID:            eventID,
		GatewayID:          gwID,
		GatewayEpoch:       epochStr,
		EventSeq:           seqStr,
		NodeID:             uint8(nodeID),
		SuperframeSeq:      1,
		SeqNum:             1,
		ScheduleVersion:    1,
		Severity:           severity,
		ObservedAt:         &observedAt,
		ObservedTimeSource: domain.TimeSourceGatewayUTC,
		RadioRxMonotonicUS: fmt.Sprintf("%d", time.Now().UnixMicro()),
		Buffered:           false,
		RadioAckSent:       true,
		Data: domain.EventData{
			EventRef:   uint32(now.Unix()),
			EventCode:  eventCode,
			EventValue: eventValue,
		},
		RawPayloadSHA256: rawHash,
		IngestedAt:       now,
		AckStatus:        domain.AckStatusUnacknowledged,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Update ephemeral node presence in RAM (0 disk writes)
	if s.presenceTracker != nil {
		s.presenceTracker.SetNodeStatus(nodeID, true)
	}

	// Ingest optional RF metrics from alert envelope (Issue #392 / #393)
	if rfRaw, ok := wire["rf"].(map[string]interface{}); ok && rfRaw != nil {
		s.ingestAlertRF(gwID, nodeID, rfRaw, epochStr, seqStr)
	}

	if s.eventStore != nil {
		if _, err := s.eventStore.RecordEvent(ctx, evt); err != nil {
			log.Printf("[MQTT Subscriber] Failed to record event in DB: %v", err)
		} else {
			log.Printf("[MQTT Subscriber] Event recorded successfully: node=%d code=%d val=%d", nodeID, eventCode, eventValue)
		}
	}

	// Broadcast via WebSocket Hub
	if s.hub != nil {
		triggeredAtStr := observedAt.Format(time.RFC3339)
		alertIDStr := fmt.Sprintf("%d", now.UnixNano())
		_ = s.hub.BroadcastAlert(context.Background(), realtime.AlertTriggeredPayload{
			GatewayID:   gwID,
			NodeID:      uint8(nodeID),
			AlertID:     alertIDStr,
			EventRef:    uint32(now.Unix()),
			EventCode:   eventCode,
			EventValue:  eventValue,
			Severity:    string(severity),
			TriggeredAt: &triggeredAtStr,
		})
	}
}

// DeduplicatingJoinStore is an optional interface implemented by storages that track whether a join request is new.
type DeduplicatingJoinStore interface {
	CreateOrUpdateJoinRequest(ctx context.Context, req *domain.DeviceJoinRequest) (*domain.DeviceJoinRequest, bool, error)
}

// handleJoinMessage processes node join requests from Gateway over MQTT.
func (s *GatewayStatusSubscriber) handleJoinMessage(client paho.Client, msg paho.Message) {
	topic := msg.Topic()
	payload := msg.Payload()
	log.Printf("[MQTT Subscriber] Received join message on %s: %s", topic, string(payload))

	matches := joinTopicPattern.FindStringSubmatch(topic)
	if len(matches) < 2 {
		return
	}
	gwID := matches[1]

	var wire JoinRelayPayload
	if err := json.Unmarshal(payload, &wire); err != nil {
		log.Printf("[MQTT Subscriber] Failed to unmarshal join payload: %v", err)
		return
	}

	mac := strings.ToLower(strings.TrimSpace(wire.DeviceMAC))
	if mac == "" && len(wire.RawFrameHex) >= 14 {
		// Extract MAC from raw_frame_hex byte 1..6
		rawBytes, err := hex.DecodeString(wire.RawFrameHex)
		if err == nil && len(rawBytes) >= 7 {
			mac = hex.EncodeToString(rawBytes[1:7])
		}
	}
	if len(mac) != 12 {
		log.Printf("[MQTT Subscriber] Join message with invalid MAC: %q", mac)
		return
	}

	log.Printf("[MQTT Subscriber] Node join request: gw=%s mac=%s rssi=%d snr=%.1f", gwID, mac, wire.RSSI, wire.SNR)

	if s.joinReqStore != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		isRegistered, err := s.joinReqStore.IsDeviceRegistered(ctx, mac)
		if err != nil {
			log.Printf("[MQTT Subscriber] Failed to check device registration for %s: %v", mac, err)
			return
		}
		if !isRegistered {
			log.Printf("[MQTT Subscriber] Dropping join request from unregistered device: mac=%s", mac)
			return
		}

		req := &domain.DeviceJoinRequest{
			DeviceMAC:   mac,
			GatewayID:   gwID,
			RSSI:        wire.RSSI,
			SNR:         wire.SNR,
			RawFrameHex: wire.RawFrameHex,
		}

		var saved *domain.DeviceJoinRequest
		var isNew bool
		if dedupStore, ok := s.joinReqStore.(DeduplicatingJoinStore); ok {
			sReq, isNewReq, err := dedupStore.CreateOrUpdateJoinRequest(ctx, req)
			if err != nil {
				log.Printf("[MQTT Subscriber] Failed to save pending join request: %v", err)
				return
			}
			saved = sReq
			isNew = isNewReq
		} else {
			sReq, err := s.joinReqStore.CreateOrUpdatePendingRequest(ctx, req)
			if err != nil {
				log.Printf("[MQTT Subscriber] Failed to save pending join request: %v", err)
				return
			}
			saved = sReq
			isNew = (saved != nil && saved.CreatedAt.Equal(saved.UpdatedAt))
		}

		// Already approved device: auto re-dispatch join-grant without sending join-wait or broadcasting UI request
		if saved != nil && saved.Status == "APPROVED" {
			if saved.AssignedNodeID != nil && *saved.AssignedNodeID > 0 && *saved.AssignedNodeID <= 254 {
				if err := s.PublishJoinGrant(ctx, gwID, mac, *saved.AssignedNodeID); err != nil {
					log.Printf("[MQTT Subscriber] Warning: failed to auto re-dispatch join-grant downlink: %v", err)
				} else {
					log.Printf("[MQTT Subscriber] Auto re-dispatched join grant downlink: gw=%s mac=%s node_id=%d", gwID, mac, *saved.AssignedNodeID)
				}
			} else {
				log.Printf("[MQTT Subscriber] Warning: approved join request missing valid assigned_node_id: gw=%s mac=%s", gwID, mac)
			}
			return
		}

		// Dispatch join-wait downlink to Gateway for pending device
		if err := s.PublishJoinWait(ctx, gwID, mac); err != nil {
			log.Printf("[MQTT Subscriber] Warning: failed to dispatch join-wait downlink: %v", err)
		} else {
			log.Printf("[MQTT Subscriber] Dispatched join wait downlink: gw=%s mac=%s", gwID, mac)
		}

		// Broadcast realtime notification to WebSocket clients ONLY if this is a newly created pending request
		if saved != nil && isNew && saved.Status == "PENDING" && s.hub != nil {
			payloadBytes, _ := json.Marshal(map[string]interface{}{
				"id":         saved.ID,
				"device_mac": saved.DeviceMAC,
				"gateway_id": saved.GatewayID,
				"rssi":       saved.RSSI,
				"snr":        saved.SNR,
				"status":     saved.Status,
				"created_at": saved.CreatedAt.Format(time.RFC3339),
			})
			envelope := &realtime.RealtimeEnvelope{
				SchemaVersion: "1.0-draft",
				EventID:       fmt.Sprintf("join-req:%s:%d", mac, time.Now().UnixNano()),
				Type:          "NODE_JOIN_REQUEST",
				EmittedAt:     time.Now().UTC().Format(time.RFC3339),
				Payload:       payloadBytes,
			}
			_ = s.hub.BroadcastEnvelope(context.Background(), envelope)
		}
	}
}

// PublishJoinWait sends a downlink wait message to the Gateway over MQTT.
func (s *GatewayStatusSubscriber) PublishJoinWait(ctx context.Context, gatewayID string, deviceMAC string) error {
	if s.client == nil || !s.client.IsConnected() {
		return fmt.Errorf("MQTT client is not connected")
	}

	topic := fmt.Sprintf("iot/v1/gw/%s/downlink/join-wait", gatewayID)
	payloadMap := map[string]interface{}{
		"gateway_id": gatewayID,
		"device_mac": deviceMAC,
		"status":     "WAIT",
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	}

	payloadBytes, err := json.Marshal(payloadMap)
	if err != nil {
		return fmt.Errorf("marshal join wait: %w", err)
	}

	token := s.client.Publish(topic, 1, false, payloadBytes)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("publish join wait error: %w", token.Error())
	}

	log.Printf("[MQTT Downlink] Successfully published join wait to %s: %s", topic, string(payloadBytes))
	return nil
}

// PublishJoinReject sends a downlink reject message to the Gateway over MQTT.
func (s *GatewayStatusSubscriber) PublishJoinReject(ctx context.Context, gatewayID string, deviceMAC string) error {
	if s.client == nil || !s.client.IsConnected() {
		return fmt.Errorf("MQTT client is not connected")
	}

	topic := fmt.Sprintf("iot/v1/gw/%s/downlink/join-reject", gatewayID)
	payloadMap := map[string]interface{}{
		"gateway_id": gatewayID,
		"device_mac": deviceMAC,
		"status":     "REJECTED",
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	}

	payloadBytes, err := json.Marshal(payloadMap)
	if err != nil {
		return fmt.Errorf("marshal join reject: %w", err)
	}

	token := s.client.Publish(topic, 1, false, payloadBytes)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("publish join reject error: %w", token.Error())
	}

	log.Printf("[MQTT Downlink] Successfully published join reject to %s: %s", topic, string(payloadBytes))
	return nil
}

// PublishJoinGrant sends a downlink grant message to the Gateway over MQTT.
func (s *GatewayStatusSubscriber) PublishJoinGrant(ctx context.Context, gatewayID string, deviceMAC string, nodeID int) error {
	if s.client == nil || !s.client.IsConnected() {
		return fmt.Errorf("MQTT client is not connected")
	}

	topic := fmt.Sprintf("iot/v1/gw/%s/downlink/join-grant", gatewayID)
	payloadMap := map[string]interface{}{
		"gateway_id": gatewayID,
		"device_mac": deviceMAC,
		"node_id":    nodeID,
		"status":     "APPROVED",
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	}

	payloadBytes, err := json.Marshal(payloadMap)
	if err != nil {
		return fmt.Errorf("marshal join grant: %w", err)
	}

	token := s.client.Publish(topic, 1, false, payloadBytes)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("publish join grant error: %w", token.Error())
	}

	log.Printf("[MQTT Downlink] Successfully published join grant to %s: %s", topic, string(payloadBytes))
	return nil
}

// PublishNodeRevoke sends a downlink revoke message to the Gateway over MQTT.
func (s *GatewayStatusSubscriber) PublishNodeRevoke(ctx context.Context, gatewayID string, nodeID int) error {
	if s.client == nil || !s.client.IsConnected() {
		return fmt.Errorf("MQTT client is not connected")
	}

	topic := fmt.Sprintf("iot/v1/gw/%s/downlink/node-revoke", gatewayID)
	payloadMap := map[string]interface{}{
		"node_id": nodeID,
	}

	payloadBytes, err := json.Marshal(payloadMap)
	if err != nil {
		return fmt.Errorf("marshal node revoke: %w", err)
	}

	token := s.client.Publish(topic, 1, false, payloadBytes)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("publish node revoke error: %w", token.Error())
	}

	log.Printf("[MQTT Downlink] Successfully published node revoke to %s: %s", topic, string(payloadBytes))
	return nil
}

// Stop closes the subscriber connection.
func (s *GatewayStatusSubscriber) Stop() {
	select {
	case <-s.stopTicker:
	default:
		close(s.stopTicker)
	}
	if s.client != nil && s.client.IsConnected() {
		s.client.Disconnect(250)
	}
}

// ingestAlertRF safely ingests physical-layer LoRa RF metrics embedded within an alert envelope.
// Any malformed or invalid field is safely ignored without impacting the alert business event.
func (s *GatewayStatusSubscriber) ingestAlertRF(gwID string, nodeID int, rfMap map[string]interface{}, defaultEpoch string, defaultSeq string) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("[MQTT Subscriber] Recovered from panic ingesting alert RF: %v", r)
		}
	}()

	s.mu.Lock()
	tracker := s.rfTracker
	s.mu.Unlock()
	if tracker == nil {
		return
	}

	rssiVal, ok := rfMap["rssi_dbm"]
	if !ok {
		return
	}
	rssiFloat, ok := rssiVal.(float64)
	if !ok {
		return
	}
	rssiDbm := int(rssiFloat)

	snrVal, ok := rfMap["snr_db"]
	if !ok {
		return
	}
	snrDb, ok := snrVal.(float64)
	if !ok {
		return
	}

	var chIdx *int
	if chVal, ok := rfMap["channel_idx"]; ok && chVal != nil {
		if chFloat, ok := chVal.(float64); ok {
			c := int(chFloat)
			chIdx = &c
		}
	}

	epoch := defaultEpoch
	if ep, ok := rfMap["gateway_epoch"].(string); ok && ep != "" {
		epoch = ep
	}

	seqStr := defaultSeq
	if sq, ok := rfMap["sample_seq"].(string); ok && sq != "" {
		seqStr = sq
	}
	sampleSeq, err := strconv.ParseUint(seqStr, 10, 64)
	if err != nil {
		return
	}

	monoUS := uint64(0)
	if mu, ok := rfMap["rx_monotonic_us"].(string); ok && mu != "" {
		monoUS, _ = strconv.ParseUint(mu, 10, 64)
	} else if mu, ok := rfMap["sample_monotonic_us"].(string); ok && mu != "" {
		monoUS, _ = strconv.ParseUint(mu, 10, 64)
	}

	source := "UP_EVENT"
	if src, ok := rfMap["source"].(string); ok && src != "" {
		source = src
	}

	validation := "VERIFIED"
	if val, ok := rfMap["validation"].(string); ok && val != "" {
		validation = val
	}

	tracker.UpdateNodeRF(gwID, nodeID, rssiDbm, snrDb, chIdx, source, validation, epoch, sampleSeq, monoUS, 0)
}

// handleRFMetricsMessage processes dedicated LoRa RF metrics publications.
// Topic: iot/v1/gw/{gateway_id}/uplink/rf-metrics
func (s *GatewayStatusSubscriber) handleRFMetricsMessage(client paho.Client, msg paho.Message) {
	topic := msg.Topic()
	payload := msg.Payload()

	match := rfMetricsTopicPattern.FindStringSubmatch(topic)
	if len(match) < 2 {
		log.Printf("[MQTT Subscriber] Invalid rf-metrics topic: %s", topic)
		return
	}
	topicGwID := match[1]

	var p RFMetricsPayload
	if err := json.Unmarshal(payload, &p); err != nil {
		log.Printf("[MQTT Subscriber] Failed to unmarshal rf-metrics payload on %s: %v", topic, err)
		return
	}

	if p.GatewayID != "" && p.GatewayID != topicGwID {
		log.Printf("[MQTT Subscriber] rf-metrics gateway_id mismatch: topic=%s payload=%s", topicGwID, p.GatewayID)
		return
	}

	gwID := topicGwID
	if p.GatewayID != "" {
		gwID = p.GatewayID
	}

	if p.GatewayEpoch == "" {
		log.Printf("[MQTT Subscriber] rf-metrics missing gateway_epoch on %s", topic)
		return
	}

	s.mu.Lock()
	tracker := s.rfTracker
	s.mu.Unlock()
	if tracker == nil {
		return
	}

	if len(p.Samples) > 0 {
		for _, smp := range p.Samples {
			s.processRFMetricSample(tracker, gwID, p.GatewayEpoch, smp)
		}
	} else {
		// Single sample envelope
		smp := RFMetricsSample{
			SampleSeq:         p.SampleSeq,
			SampleMonotonicUS: p.SampleMonotonicUS,
			AgeMs:             p.AgeMs,
			Kind:              p.Kind,
			ChannelIdx:        p.ChannelIdx,
			NodeID:            p.NodeID,
			RssiDbm:           p.RssiDbm,
			SnrDb:             p.SnrDb,
			Source:            p.Source,
			Validation:        p.Validation,
			ChannelRssiDbm:    p.ChannelRssiDbm,
			SampleContext:     p.SampleContext,
		}
		s.processRFMetricSample(tracker, gwID, p.GatewayEpoch, smp)
	}
}

func (s *GatewayStatusSubscriber) processRFMetricSample(tracker *presence.RFTracker, gwID, epoch string, smp RFMetricsSample) {
	seq, err := strconv.ParseUint(smp.SampleSeq, 10, 64)
	if err != nil {
		return
	}
	monoUS, _ := strconv.ParseUint(smp.SampleMonotonicUS, 10, 64)
	ageMs := uint32(0)
	if smp.AgeMs != nil {
		ageMs = *smp.AgeMs
	}

	switch smp.Kind {
	case "NODE_UPLINK":
		if smp.NodeID == nil || smp.RssiDbm == nil || smp.SnrDb == nil {
			return
		}
		tracker.UpdateNodeRF(
			gwID,
			*smp.NodeID,
			*smp.RssiDbm,
			*smp.SnrDb,
			smp.ChannelIdx,
			smp.Source,
			smp.Validation,
			epoch,
			seq,
			monoUS,
			ageMs,
		)
	case "CHANNEL":
		if smp.ChannelIdx == nil || smp.ChannelRssiDbm == nil {
			return
		}
		tracker.UpdateChannelRF(
			gwID,
			*smp.ChannelIdx,
			*smp.ChannelRssiDbm,
			smp.SampleContext,
			epoch,
			seq,
			monoUS,
			ageMs,
		)
	}
}
