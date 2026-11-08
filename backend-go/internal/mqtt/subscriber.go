package mqtt

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"regexp"
	"strings"
	"sync"
	"time"

	paho "github.com/eclipse/paho.mqtt.golang"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var statusTopicPattern = regexp.MustCompile(`^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/status$`)

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

// GatewayStatusSubscriber subscribes to MQTT gateway status topics and updates the persistent database.
type GatewayStatusSubscriber struct {
	client         paho.Client
	store          storage.StatusStorage
	hub            *realtime.Hub
	brokerURI      string
	mu             sync.Mutex
	onlineGateways map[string]*LiveStatusPayload
	stopTicker     chan struct{}
}

// NewGatewayStatusSubscriber creates a new status subscriber for operational monitoring.
func NewGatewayStatusSubscriber(brokerURI string, store storage.StatusStorage, hub *realtime.Hub) *GatewayStatusSubscriber {
	return &GatewayStatusSubscriber{
		brokerURI:      brokerURI,
		store:          store,
		hub:            hub,
		onlineGateways: make(map[string]*LiveStatusPayload),
		stopTicker:     make(chan struct{}),
	}
}

// Start begins listening to MQTT gateway status publications asynchronously.
func (s *GatewayStatusSubscriber) Start(ctx context.Context) error {
	opts := paho.NewClientOptions()
	opts.AddBroker(s.brokerURI)
	opts.SetClientID(fmt.Sprintf("backend-gw-sub-%d", time.Now().UnixNano()%100000))
	opts.SetAutoReconnect(true)
	opts.SetKeepAlive(30 * time.Second)
	opts.SetOnConnectHandler(func(c paho.Client) {
		log.Printf("[MQTT Subscriber] Connected to broker %s; subscribing to iot/v1/gw/+/uplink/status", s.brokerURI)
		token := c.Subscribe("iot/v1/gw/+/uplink/status", 1, s.handleMessage)
		if token.Wait() && token.Error() != nil {
			log.Printf("[MQTT Subscriber] Subscribe error: %v", token.Error())
		}
	})
	opts.SetConnectionLostHandler(func(c paho.Client, err error) {
		log.Printf("[MQTT Subscriber] Broker connection lost: %v", err)
		s.mu.Lock()
		s.onlineGateways = make(map[string]*LiveStatusPayload)
		s.mu.Unlock()
	})

	client := paho.NewClient(opts)
	token := client.Connect()
	if token.Wait() && token.Error() != nil {
		log.Printf("[MQTT Subscriber] Initial connect returned: %v (will retry in background)", token.Error())
	}
	s.client = client

	// Periodic keep-alive refresh for active gateways so offlineThreshold (>5m) is not exceeded while online
	go func() {
		ticker := time.NewTicker(60 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-s.stopTicker:
				return
			case <-ticker.C:
				s.refreshOnlineGateways()
			}
		}
	}()

	return nil
}

func (s *GatewayStatusSubscriber) refreshOnlineGateways() {
	s.mu.Lock()
	gws := make([]*LiveStatusPayload, 0, len(s.onlineGateways))
	for _, p := range s.onlineGateways {
		gws = append(gws, p)
	}
	s.mu.Unlock()

	if len(gws) == 0 {
		return
	}

	now := time.Now().UTC()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	for _, wire := range gws {
		chID := "CH00"
		if wire.ChannelID != "" {
			chID = wire.ChannelID
		}
		record := &domain.GatewayStatusRecord{
			GatewayID:             wire.GatewayID,
			GatewayEpoch:          "00000000-0000-0000-0000-000000000001",
			Mode:                  domain.GatewayModeActive,
			ActiveScheduleVersion: wire.ActiveScheduleVersion,
			ChannelID:             &chID,
			RFDutyPermille:        wire.RFDutyPermille,
			NodeCount:             wire.NodeCount,
			FreeHeapBytes:         uint64(wire.FreeHeapBytes),
			LastSeenAt:            now,
			UpdatedAt:             now,
		}
		_ = s.store.UpsertGatewayStatus(ctx, record)
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

	s.mu.Lock()
	if mode == domain.GatewayModeActive {
		s.onlineGateways[wire.GatewayID] = &wire
	} else {
		delete(s.onlineGateways, wire.GatewayID)
	}
	s.mu.Unlock()

	chID := "CH00"
	if wire.ChannelID != "" {
		chID = wire.ChannelID
	}

	now := time.Now().UTC()
	record := &domain.GatewayStatusRecord{
		GatewayID:             wire.GatewayID,
		GatewayEpoch:          "00000000-0000-0000-0000-000000000001",
		Mode:                  mode,
		ActiveScheduleVersion: wire.ActiveScheduleVersion,
		ChannelID:             &chID,
		RFDutyPermille:        wire.RFDutyPermille,
		NodeCount:             wire.NodeCount,
		FreeHeapBytes:         uint64(wire.FreeHeapBytes),
		LastSeenAt:            now,
		UpdatedAt:             now,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := s.store.UpsertGatewayStatus(ctx, record); err != nil {
		log.Printf("[MQTT Subscriber] Failed to update gateway status for %s: %v", wire.GatewayID, err)
		return
	}

	log.Printf("[MQTT Subscriber] Gateway %s is now recorded as %s (last_seen=%s)", wire.GatewayID, mode, now.Format(time.RFC3339))

	if s.hub != nil {
		lastSeenStr := now.Format(time.RFC3339)
		if err := s.hub.BroadcastGatewayStatus(context.Background(), realtime.GatewayStatusChangedPayload{
			GatewayID:  wire.GatewayID,
			Mode:       string(mode),
			LastSeenAt: &lastSeenStr,
		}); err != nil {
			log.Printf("[MQTT Subscriber] Failed to broadcast gateway status event: %v", err)
		}
	}
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
