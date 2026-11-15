package mqtt

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	paho "github.com/eclipse/paho.mqtt.golang"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/presence"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockMessage struct {
	topic   string
	payload []byte
}

func (m *mockMessage) Duplicate() bool   { return false }
func (m *mockMessage) Qos() byte         { return 1 }
func (m *mockMessage) Retained() bool    { return false }
func (m *mockMessage) Topic() string     { return m.topic }
func (m *mockMessage) MessageID() uint16 { return 1 }
func (m *mockMessage) Payload() []byte   { return m.payload }
func (m *mockMessage) Ack()              {}

type mockJoinReqStorage struct {
	isRegisteredCalled bool
	lastCheckedMAC     string
	isRegistered       bool
	checkErr           error

	createdReq *domain.DeviceJoinRequest
	createErr  error

	customReq *domain.DeviceJoinRequest
	isNew     bool
}

func (m *mockJoinReqStorage) IsDeviceRegistered(ctx context.Context, mac string) (bool, error) {
	m.isRegisteredCalled = true
	m.lastCheckedMAC = mac
	return m.isRegistered, m.checkErr
}

func (m *mockJoinReqStorage) CreateOrUpdateJoinRequest(ctx context.Context, req *domain.DeviceJoinRequest) (*domain.DeviceJoinRequest, bool, error) {
	if m.createErr != nil {
		return nil, false, m.createErr
	}
	m.createdReq = req
	if m.customReq != nil {
		return m.customReq, m.isNew, nil
	}
	now := time.Now().UTC()
	return &domain.DeviceJoinRequest{
		ID:          101,
		DeviceMAC:   req.DeviceMAC,
		GatewayID:   req.GatewayID,
		RSSI:        req.RSSI,
		SNR:         req.SNR,
		RawFrameHex: req.RawFrameHex,
		Status:      "PENDING",
		CreatedAt:   now,
		UpdatedAt:   now,
	}, true, nil
}

func (m *mockJoinReqStorage) CreateOrUpdatePendingRequest(ctx context.Context, req *domain.DeviceJoinRequest) (*domain.DeviceJoinRequest, error) {
	saved, _, err := m.CreateOrUpdateJoinRequest(ctx, req)
	return saved, err
}

func (m *mockJoinReqStorage) ListPendingRequests(ctx context.Context) ([]*domain.DeviceJoinRequest, error) {
	return nil, nil
}

func (m *mockJoinReqStorage) ApproveRequest(ctx context.Context, id int64, requestedNodeID *int) (*domain.DeviceJoinRequest, error) {
	return nil, nil
}

func (m *mockJoinReqStorage) RejectRequest(ctx context.Context, id int64) error {
	return nil
}

func TestHandleJoinMessage_UnregisteredDevice_Dropped(t *testing.T) {
	// Capture log to verify silent drop log output
	var buf bytes.Buffer
	log.SetOutput(&buf)
	defer log.SetOutput(os.Stderr)

	mockStore := &mockJoinReqStorage{
		isRegistered: false,
	}
	hub := realtime.NewHub()
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, hub, nil, mockStore, nil)

	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID: "gw-test-01",
		DeviceMAC: "aabbccddeeff",
		RSSI:      -80,
		SNR:       9.5,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-test-01/uplink/join-hello",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	if !mockStore.isRegisteredCalled {
		t.Fatal("expected IsDeviceRegistered to be called")
	}
	if mockStore.lastCheckedMAC != "aabbccddeeff" {
		t.Fatalf("expected checked MAC to be aabbccddeeff, got %s", mockStore.lastCheckedMAC)
	}
	if mockStore.createdReq != nil {
		t.Fatal("expected CreateOrUpdatePendingRequest NOT to be called for unregistered device")
	}

	// Verify exact log output
	logOutput := buf.String()
	expectedLog := "[MQTT Subscriber] Dropping join request from unregistered device: mac=aabbccddeeff"
	if !strings.Contains(logOutput, expectedLog) {
		t.Fatalf("expected log to contain %q, got: %s", expectedLog, logOutput)
	}
}

func TestHandleJoinMessage_RegisteredDevice_PendingAndBroadcast(t *testing.T) {
	mockStore := &mockJoinReqStorage{
		isRegistered: true,
	}
	hub := realtime.NewHub()
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, hub, nil, mockStore, nil)

	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID: "gw-test-01",
		DeviceMAC: "aabbccddeeff",
		RSSI:      -75,
		SNR:       10.2,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-test-01/uplink/join-request",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	if !mockStore.isRegisteredCalled {
		t.Fatal("expected IsDeviceRegistered to be called")
	}
	if mockStore.createdReq == nil {
		t.Fatal("expected CreateOrUpdatePendingRequest to be called for registered device")
	}
	if mockStore.createdReq.DeviceMAC != "aabbccddeeff" {
		t.Fatalf("expected MAC aabbccddeeff, got %s", mockStore.createdReq.DeviceMAC)
	}
	if mockStore.createdReq.GatewayID != "gw-test-01" {
		t.Fatalf("expected GatewayID gw-test-01, got %s", mockStore.createdReq.GatewayID)
	}
	if mockStore.createdReq.RSSI != -75 || mockStore.createdReq.SNR != 10.2 {
		t.Fatalf("unexpected RF metrics: RSSI=%d, SNR=%.1f", mockStore.createdReq.RSSI, mockStore.createdReq.SNR)
	}
}

func TestHandleJoinMessage_InvalidMAC_Dropped(t *testing.T) {
	mockStore := &mockJoinReqStorage{
		isRegistered: true,
	}
	hub := realtime.NewHub()
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, hub, nil, mockStore, nil)

	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID: "gw-test-01",
		DeviceMAC: "short",
		RSSI:      -75,
		SNR:       10.2,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-test-01/uplink/join-request",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	if mockStore.isRegisteredCalled {
		t.Fatal("expected IsDeviceRegistered NOT to be called for invalid MAC")
	}
	if mockStore.createdReq != nil {
		t.Fatal("expected CreateOrUpdatePendingRequest NOT to be called for invalid MAC")
	}
}

func TestHandleJoinMessage_StorageError_SafeReturn(t *testing.T) {
	mockStore := &mockJoinReqStorage{
		checkErr: errors.New("database connection refused"),
	}
	hub := realtime.NewHub()
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, hub, nil, mockStore, nil)

	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID: "gw-test-01",
		DeviceMAC: "aabbccddeeff",
		RSSI:      -75,
		SNR:       10.2,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-test-01/uplink/join-request",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	if !mockStore.isRegisteredCalled {
		t.Fatal("expected IsDeviceRegistered to be called")
	}
	if mockStore.createdReq != nil {
		t.Fatal("expected CreateOrUpdatePendingRequest NOT to be called on storage error")
	}
}

func TestHandleJoinMessage_ExtractMACFromRawFrame(t *testing.T) {
	mockStore := &mockJoinReqStorage{
		isRegistered: true,
	}
	hub := realtime.NewHub()
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, hub, nil, mockStore, nil)

	// Raw frame hex: VER_TYPE(0x45) + MAC(6 bytes: 010203040506) + extra payload
	rawHex := "450102030405060708090a0b0c0d0e"
	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID:   "gw-test-01",
		DeviceMAC:   "",
		RawFrameHex: rawHex,
		RSSI:        -82,
		SNR:         8.0,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-test-01/uplink/join-hello",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	if !mockStore.isRegisteredCalled {
		t.Fatal("expected IsDeviceRegistered to be called")
	}
	if mockStore.lastCheckedMAC != "010203040506" {
		t.Fatalf("expected extracted MAC 010203040506, got %s", mockStore.lastCheckedMAC)
	}
	if mockStore.createdReq == nil {
		t.Fatal("expected CreateOrUpdatePendingRequest to be called")
	}
	if mockStore.createdReq.DeviceMAC != "010203040506" {
		t.Fatalf("expected MAC 010203040506, got %s", mockStore.createdReq.DeviceMAC)
	}
}

func TestPublishNodeRevoke_DisconnectedClient_ReturnsError(t *testing.T) {
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, nil, nil)
	err := subscriber.PublishNodeRevoke(context.Background(), "gw-test-01", 42)
	if err == nil {
		t.Fatal("expected error when MQTT client is not connected")
	}
}

type mockMqttToken struct {
	paho.Token
	err error
}

func (t *mockMqttToken) Wait() bool                       { return true }
func (t *mockMqttToken) WaitTimeout(d time.Duration) bool { return true }
func (t *mockMqttToken) Error() error                     { return t.err }

type mockMqttClient struct {
	paho.Client
	connected bool
	published map[string][]byte
}

func (c *mockMqttClient) IsConnected() bool { return c.connected }

func (c *mockMqttClient) Publish(topic string, qos byte, retained bool, payload interface{}) paho.Token {
	if c.published == nil {
		c.published = make(map[string][]byte)
	}
	switch p := payload.(type) {
	case []byte:
		c.published[topic] = p
	case string:
		c.published[topic] = []byte(p)
	default:
		b, _ := json.Marshal(p)
		c.published[topic] = b
	}
	return &mockMqttToken{}
}

type mockHub struct {
	envelopes []*realtime.RealtimeEnvelope
}

func (m *mockHub) BroadcastEnvelope(ctx context.Context, env *realtime.RealtimeEnvelope) error {
	m.envelopes = append(m.envelopes, env)
	return nil
}

func (m *mockHub) BroadcastGatewayStatus(ctx context.Context, payload realtime.GatewayStatusChangedPayload) error {
	return nil
}

func (m *mockHub) BroadcastAlert(ctx context.Context, payload realtime.AlertTriggeredPayload) error {
	return nil
}

func TestPublishJoinWait_DisconnectedClient_ReturnsError(t *testing.T) {
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, nil, nil)
	err := subscriber.PublishJoinWait(context.Background(), "gw-test-01", "aabbccddeeff")
	if err == nil {
		t.Fatal("expected error when MQTT client is not connected")
	}
}

func TestPublishJoinReject_DisconnectedClient_ReturnsError(t *testing.T) {
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, nil, nil)
	err := subscriber.PublishJoinReject(context.Background(), "gw-test-01", "aabbccddeeff")
	if err == nil {
		t.Fatal("expected error when MQTT client is not connected")
	}
}

func TestPublishJoinWait_Success(t *testing.T) {
	mockClient := &mockMqttClient{connected: true}
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, nil, nil)
	subscriber.client = mockClient

	err := subscriber.PublishJoinWait(context.Background(), "gw-test-01", "aabbccddeeff")
	if err != nil {
		t.Fatalf("unexpected error publishing join wait: %v", err)
	}

	expectedTopic := "iot/v1/gw/gw-test-01/downlink/join-wait"
	payload, ok := mockClient.published[expectedTopic]
	if !ok {
		t.Fatalf("expected message on topic %s, published topics: %+v", expectedTopic, mockClient.published)
	}

	var data map[string]interface{}
	if err := json.Unmarshal(payload, &data); err != nil {
		t.Fatalf("failed to unmarshal payload: %v", err)
	}

	if data["gateway_id"] != "gw-test-01" {
		t.Errorf("expected gateway_id gw-test-01, got %v", data["gateway_id"])
	}
	if data["device_mac"] != "aabbccddeeff" {
		t.Errorf("expected device_mac aabbccddeeff, got %v", data["device_mac"])
	}
	if data["status"] != "WAIT" {
		t.Errorf("expected status WAIT, got %v", data["status"])
	}
}

func TestPublishJoinReject_Success(t *testing.T) {
	mockClient := &mockMqttClient{connected: true}
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, nil, nil)
	subscriber.client = mockClient

	err := subscriber.PublishJoinReject(context.Background(), "gw-test-01", "aabbccddeeff")
	if err != nil {
		t.Fatalf("unexpected error publishing join reject: %v", err)
	}

	expectedTopic := "iot/v1/gw/gw-test-01/downlink/join-reject"
	payload, ok := mockClient.published[expectedTopic]
	if !ok {
		t.Fatalf("expected message on topic %s, published topics: %+v", expectedTopic, mockClient.published)
	}

	var data map[string]interface{}
	if err := json.Unmarshal(payload, &data); err != nil {
		t.Fatalf("failed to unmarshal payload: %v", err)
	}

	if data["gateway_id"] != "gw-test-01" {
		t.Errorf("expected gateway_id gw-test-01, got %v", data["gateway_id"])
	}
	if data["device_mac"] != "aabbccddeeff" {
		t.Errorf("expected device_mac aabbccddeeff, got %v", data["device_mac"])
	}
	if data["status"] != "REJECTED" {
		t.Errorf("expected status REJECTED, got %v", data["status"])
	}
}

func TestHandleJoinMessage_ValidDevice_PublishesJoinWaitAndBroadcastsWS(t *testing.T) {
	mockClient := &mockMqttClient{connected: true}
	mockStore := &mockJoinReqStorage{
		isRegistered: true,
	}
	mHub := &mockHub{}

	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, mockStore, nil)
	subscriber.client = mockClient
	subscriber.hub = mHub

	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID: "gw-test-01",
		DeviceMAC: "aabbccddeeff",
		RSSI:      -75,
		SNR:       10.2,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-test-01/uplink/join-hello",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	// Verify downlink join-wait was published
	waitTopic := "iot/v1/gw/gw-test-01/downlink/join-wait"
	if _, ok := mockClient.published[waitTopic]; !ok {
		t.Fatalf("expected downlink join-wait on topic %s", waitTopic)
	}

	// Verify WebSocket broadcast occurred for new request
	if len(mHub.envelopes) != 1 {
		t.Fatalf("expected 1 WebSocket envelope broadcast, got %d", len(mHub.envelopes))
	}
	if mHub.envelopes[0].Type != "NODE_JOIN_REQUEST" {
		t.Errorf("expected envelope type NODE_JOIN_REQUEST, got %s", mHub.envelopes[0].Type)
	}
}

func TestHandleJoinMessage_Deduplication_PendingDoesNotBroadcastWS(t *testing.T) {
	mockClient := &mockMqttClient{connected: true}
	now := time.Now().UTC()
	mockStore := &mockJoinReqStorage{
		isRegistered: true,
		customReq: &domain.DeviceJoinRequest{
			ID:        10,
			DeviceMAC: "aabbccddeeff",
			GatewayID: "gw-test-01",
			Status:    "PENDING",
			CreatedAt: now.Add(-time.Minute),
			UpdatedAt: now,
		},
		isNew: false, // duplicate pending request
	}
	mHub := &mockHub{}

	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, mockStore, nil)
	subscriber.client = mockClient
	subscriber.hub = mHub

	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID: "gw-test-01",
		DeviceMAC: "aabbccddeeff",
		RSSI:      -75,
		SNR:       10.2,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-test-01/uplink/join-hello",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	// Verify downlink join-wait was still published to keep node in rxsingle
	waitTopic := "iot/v1/gw/gw-test-01/downlink/join-wait"
	if _, ok := mockClient.published[waitTopic]; !ok {
		t.Fatalf("expected downlink join-wait on topic %s", waitTopic)
	}

	// Verify WebSocket broadcast was suppressed for duplicate pending request
	if len(mHub.envelopes) != 0 {
		t.Fatalf("expected 0 WebSocket envelope broadcasts for duplicate pending request, got %d", len(mHub.envelopes))
	}
}

func TestHandleJoinMessage_Deduplication_ApprovedDoesNotBroadcastWS(t *testing.T) {
	mockClient := &mockMqttClient{connected: true}
	now := time.Now().UTC()
	nodeID := 4
	mockStore := &mockJoinReqStorage{
		isRegistered: true,
		customReq: &domain.DeviceJoinRequest{
			ID:             10,
			DeviceMAC:      "aabbccddeeff",
			GatewayID:      "gw-test-01",
			Status:         "APPROVED",
			AssignedNodeID: &nodeID,
			CreatedAt:      now.Add(-time.Hour),
			UpdatedAt:      now,
		},
		isNew: false, // already approved
	}
	mHub := &mockHub{}

	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, mockStore, nil)
	subscriber.client = mockClient
	subscriber.hub = mHub

	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID: "gw-test-01",
		DeviceMAC: "aabbccddeeff",
		RSSI:      -75,
		SNR:       10.2,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-test-01/uplink/join-hello",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	// Verify join-wait was NOT published for an already-approved device
	waitTopic := "iot/v1/gw/gw-test-01/downlink/join-wait"
	if _, ok := mockClient.published[waitTopic]; ok {
		t.Fatalf("expected NO downlink join-wait for already approved device")
	}

	// Verify downlink join-grant WAS automatically re-dispatched
	grantTopic := "iot/v1/gw/gw-test-01/downlink/join-grant"
	grantPayload, ok := mockClient.published[grantTopic]
	if !ok {
		t.Fatalf("expected auto re-dispatched join-grant on topic %s", grantTopic)
	}
	var grantData map[string]interface{}
	if err := json.Unmarshal(grantPayload, &grantData); err != nil {
		t.Fatalf("failed to unmarshal grant payload: %v", err)
	}
	if grantData["gateway_id"] != "gw-test-01" {
		t.Errorf("expected gateway_id gw-test-01, got %v", grantData["gateway_id"])
	}
	if grantData["device_mac"] != "aabbccddeeff" {
		t.Errorf("expected device_mac aabbccddeeff, got %v", grantData["device_mac"])
	}
	if grantData["node_id"] != float64(4) {
		t.Errorf("expected node_id 4, got %v", grantData["node_id"])
	}
	if grantData["status"] != "APPROVED" {
		t.Errorf("expected status APPROVED, got %v", grantData["status"])
	}

	// Verify WebSocket broadcast was suppressed for already approved device
	if len(mHub.envelopes) != 0 {
		t.Fatalf("expected 0 WebSocket envelope broadcasts for already approved device, got %d", len(mHub.envelopes))
	}
}

func TestHandleJoinMessage_ApprovedWithRawFrameHexOnly_ReDispatchesGrantWithoutWS(t *testing.T) {
	mockClient := &mockMqttClient{connected: true}
	now := time.Now().UTC()
	nodeID := 1
	mockStore := &mockJoinReqStorage{
		isRegistered: true,
		customReq: &domain.DeviceJoinRequest{
			ID:             22,
			DeviceMAC:      "a0b765cdb33c",
			GatewayID:      "gw-a",
			Status:         "APPROVED",
			AssignedNodeID: &nodeID,
			CreatedAt:      now.Add(-time.Minute),
			UpdatedAt:      now,
		},
		isNew: false,
	}
	mHub := &mockHub{}

	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, mockStore, nil)
	subscriber.client = mockClient
	subscriber.hub = mHub

	// Matches gateway_v2_join_build_relay_json where device_mac is omitted and extracted from raw_frame_hex[1:7]
	rawHex := "45a0b765cdb33c0100000002" + strings.Repeat("aa", 56)
	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID:   "gw-a",
		RawFrameHex: rawHex,
		RSSI:        -61,
		SNR:         6.2,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-a/uplink/join-hello",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	if _, ok := mockClient.published["iot/v1/gw/gw-a/downlink/join-wait"]; ok {
		t.Fatalf("expected NO downlink join-wait when device is already APPROVED")
	}
	grantPayload, ok := mockClient.published["iot/v1/gw/gw-a/downlink/join-grant"]
	if !ok {
		t.Fatalf("expected downlink join-grant on iot/v1/gw/gw-a/downlink/join-grant")
	}
	var grantData map[string]interface{}
	if err := json.Unmarshal(grantPayload, &grantData); err != nil {
		t.Fatalf("failed to unmarshal grant payload: %v", err)
	}
	if grantData["device_mac"] != "a0b765cdb33c" || grantData["node_id"] != float64(1) {
		t.Fatalf("unexpected grant payload: %+v", grantData)
	}
	if len(mHub.envelopes) != 0 {
		t.Fatalf("expected 0 WebSocket broadcasts for already approved device, got %d", len(mHub.envelopes))
	}
}

func TestHandleJoinMessage_ApprovedInvalidNodeID_DoesNotPublishWaitOrGrant(t *testing.T) {
	mockClient := &mockMqttClient{connected: true}
	now := time.Now().UTC()
	mockStore := &mockJoinReqStorage{
		isRegistered: true,
		customReq: &domain.DeviceJoinRequest{
			ID:             33,
			DeviceMAC:      "aabbccddeeff",
			GatewayID:      "gw-test-01",
			Status:         "APPROVED",
			AssignedNodeID: nil,
			CreatedAt:      now.Add(-time.Minute),
			UpdatedAt:      now,
		},
		isNew: false,
	}
	mHub := &mockHub{}

	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, mockStore, nil)
	subscriber.client = mockClient
	subscriber.hub = mHub

	payloadBytes, _ := json.Marshal(JoinRelayPayload{
		GatewayID: "gw-test-01",
		DeviceMAC: "aabbccddeeff",
		RSSI:      -75,
		SNR:       10.2,
	})
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-test-01/uplink/join-hello",
		payload: payloadBytes,
	}

	subscriber.handleJoinMessage(nil, msg)

	if len(mockClient.published) != 0 {
		t.Fatalf("expected no MQTT downlink publications when assigned_node_id is nil, got: %+v", mockClient.published)
	}
	if len(mHub.envelopes) != 0 {
		t.Fatalf("expected 0 WebSocket broadcasts, got %d", len(mHub.envelopes))
	}
}

func TestHandleRFMetricsMessage_NodeUplink_NegativeAndZeroSNR(t *testing.T) {
	tracker := presence.NewRFTracker()
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, nil, nil)
	subscriber.SetRFTracker(tracker)

	// 1. Ingest sample with negative SNR (-7.75 dB)
	payload1 := `{
		"schema_version": "1.0-draft",
		"gateway_id": "gw01",
		"gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
		"sample_seq": "1001",
		"sample_monotonic_us": "1234567890",
		"age_ms": 15,
		"kind": "NODE_UPLINK",
		"channel_idx": 4,
		"node_id": 12,
		"rssi_dbm": -88,
		"snr_db": -7.75,
		"source": "UP_EVENT",
		"validation": "VERIFIED"
	}`
	msg1 := &mockMessage{
		topic:   "iot/v1/gw/gw01/uplink/rf-metrics",
		payload: []byte(payload1),
	}
	subscriber.handleRFMetricsMessage(nil, msg1)

	view1 := tracker.GetNodeRFView("gw01", 12)
	if view1 == nil {
		t.Fatalf("expected node RF view for node 12, got nil")
	}
	if view1.RssiDbm != -88 {
		t.Errorf("expected rssi -88, got %d", view1.RssiDbm)
	}
	if view1.SnrDb != -7.75 {
		t.Errorf("expected snr -7.75, got %v", view1.SnrDb)
	}
	if view1.ChannelIdx == nil || *view1.ChannelIdx != 4 {
		t.Errorf("expected channel_idx 4, got %v", view1.ChannelIdx)
	}
	if view1.Source != "UP_EVENT" || view1.Validation != "VERIFIED" {
		t.Errorf("unexpected source/validation: %s/%s", view1.Source, view1.Validation)
	}

	// 2. Ingest next sample with exact 0.0 SNR
	payload2 := `{
		"schema_version": "1.0-draft",
		"gateway_id": "gw01",
		"gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
		"sample_seq": "1002",
		"sample_monotonic_us": "1234570000",
		"age_ms": 10,
		"kind": "NODE_UPLINK",
		"channel_idx": 4,
		"node_id": 12,
		"rssi_dbm": -79,
		"snr_db": 0.0,
		"source": "UP_HEARTBEAT_ACK",
		"validation": "VERIFIED"
	}`
	msg2 := &mockMessage{
		topic:   "iot/v1/gw/gw01/uplink/rf-metrics",
		payload: []byte(payload2),
	}
	subscriber.handleRFMetricsMessage(nil, msg2)

	view2 := tracker.GetNodeRFView("gw01", 12)
	if view2 == nil {
		t.Fatalf("expected node RF view for node 12, got nil")
	}
	if view2.RssiDbm != -79 {
		t.Errorf("expected rssi -79, got %d", view2.RssiDbm)
	}
	if view2.SnrDb != 0.0 {
		t.Errorf("expected snr 0.0, got %v", view2.SnrDb)
	}
}

func TestHandleRFMetricsMessage_TopicPayloadGatewayMismatch(t *testing.T) {
	tracker := presence.NewRFTracker()
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, nil, nil)
	subscriber.SetRFTracker(tracker)

	payload := `{
		"schema_version": "1.0-draft",
		"gateway_id": "gw-mismatch",
		"gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
		"sample_seq": "1001",
		"sample_monotonic_us": "1234567890",
		"kind": "NODE_UPLINK",
		"node_id": 12,
		"rssi_dbm": -88,
		"snr_db": 5.0
	}`
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw01/uplink/rf-metrics",
		payload: []byte(payload),
	}
	subscriber.handleRFMetricsMessage(nil, msg)

	if view := tracker.GetNodeRFView("gw01", 12); view != nil {
		t.Fatalf("expected nil view due to gateway mismatch, got %+v", view)
	}
}

func TestHandleRFMetricsMessage_ChannelEnergy(t *testing.T) {
	tracker := presence.NewRFTracker()
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, nil, nil)
	subscriber.SetRFTracker(tracker)

	payload := `{
		"schema_version": "1.0-draft",
		"gateway_id": "gw01",
		"gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
		"sample_seq": "1002",
		"sample_monotonic_us": "1234570000",
		"age_ms": 20,
		"kind": "CHANNEL",
		"channel_idx": 0,
		"channel_rssi_dbm": -108,
		"sample_context": "RX_IDLE"
	}`
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw01/uplink/rf-metrics",
		payload: []byte(payload),
	}
	subscriber.handleRFMetricsMessage(nil, msg)

	chView := tracker.GetChannelRFView("gw01", 0)
	if chView == nil {
		t.Fatalf("expected channel RF view for gw01 ch0, got nil")
	}
	if chView.ChannelRssiDbm != -108 {
		t.Errorf("expected channel rssi -108, got %d", chView.ChannelRssiDbm)
	}
	if chView.SampleContext != "RX_IDLE" {
		t.Errorf("expected RX_IDLE, got %s", chView.SampleContext)
	}
}

func TestHandleRFMetricsMessage_BatchedSamples(t *testing.T) {
	tracker := presence.NewRFTracker()
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, nil, nil, nil)
	subscriber.SetRFTracker(tracker)

	payload := `{
		"schema_version": "1.0-draft",
		"gateway_id": "gw01",
		"gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
		"samples": [
			{
				"sample_seq": "2001",
				"sample_monotonic_us": "1234571000",
				"age_ms": 10,
				"kind": "NODE_UPLINK",
				"channel_idx": 1,
				"node_id": 5,
				"rssi_dbm": -72,
				"snr_db": 0.0,
				"source": "UP_HEARTBEAT_ACK",
				"validation": "VERIFIED"
			},
			{
				"sample_seq": "2002",
				"sample_monotonic_us": "1234572000",
				"age_ms": 5,
				"kind": "CHANNEL",
				"channel_idx": 1,
				"channel_rssi_dbm": -102,
				"sample_context": "RX_ACTIVE"
			}
		]
	}`
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw01/uplink/rf-metrics",
		payload: []byte(payload),
	}
	subscriber.handleRFMetricsMessage(nil, msg)

	nodeView := tracker.GetNodeRFView("gw01", 5)
	if nodeView == nil {
		t.Fatalf("expected node RF view for node 5, got nil")
	}
	if nodeView.RssiDbm != -72 || nodeView.SnrDb != 0.0 {
		t.Errorf("unexpected node RF view: %+v", nodeView)
	}

	chView := tracker.GetChannelRFView("gw01", 1)
	if chView == nil {
		t.Fatalf("expected channel RF view for gw01 ch1, got nil")
	}
	if chView.ChannelRssiDbm != -102 || chView.SampleContext != "RX_ACTIVE" {
		t.Errorf("unexpected channel RF view: %+v", chView)
	}
}

type mockEventStore struct {
	mu       sync.Mutex
	recorded *domain.Event
}

func (m *mockEventStore) RecordEvent(ctx context.Context, event *domain.Event) (*storage.EventRecordResult, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.recorded = event
	return &storage.EventRecordResult{EventID: 1, IsDuplicate: false, Status: "INSERTED"}, nil
}

func (m *mockEventStore) GetEvent(ctx context.Context, gatewayID, eventID string) (*domain.Event, error) {
	return nil, nil
}

func (m *mockEventStore) QuarantineEvent(ctx context.Context, q *storage.QuarantineRecord) error {
	return nil
}

func (m *mockEventStore) RecordHealthUpdate(ctx context.Context, h *domain.NodeHealth) error {
	return nil
}

func (m *mockEventStore) GetNodeHealth(ctx context.Context, gatewayID string, nodeID uint8) (*domain.NodeHealth, error) {
	return nil, nil
}

func TestHandleAlertMessage_WithValidRF(t *testing.T) {
	tracker := presence.NewRFTracker()
	mockEvtStore := &mockEventStore{}
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, mockEvtStore, nil, nil)
	subscriber.SetRFTracker(tracker)

	payload := `{
		"schema_version": "1.0-draft",
		"event_id": "gw01:550e8400-e29b-41d4-a716-446655440000:43",
		"gateway_id": "gw01",
		"gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
		"event_seq": "43",
		"observed_at": "2026-11-14T08:00:00Z",
		"observed_time_source": "gateway_utc",
		"radio_rx_monotonic_us": "123456789",
		"buffered": false,
		"node_id": 7,
		"superframe_seq": 101,
		"seq_num": 52,
		"schedule_version": 5,
		"severity": "P1_HIGH",
		"data": {
			"event_ref": 1001,
			"event_code": 1,
			"event_value": 1,
			"observed_at": "2026-11-14T08:00:00Z"
		},
		"radio_ack_sent": true,
		"rf": {
			"rssi_dbm": -82,
			"snr_db": -7.75,
			"channel_idx": 3,
			"rx_monotonic_us": "123456789",
			"gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
			"sample_seq": "1007"
		}
	}`
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw01/uplink/alert",
		payload: []byte(payload),
	}
	subscriber.handleAlertMessage(nil, msg)

	mockEvtStore.mu.Lock()
	recorded := mockEvtStore.recorded
	mockEvtStore.mu.Unlock()

	if recorded == nil {
		t.Fatalf("expected alert event to be recorded in DB")
	}
	if recorded.NodeID != 7 {
		t.Errorf("expected recorded node_id 7, got %d", recorded.NodeID)
	}

	view := tracker.GetNodeRFView("gw01", 7)
	if view == nil {
		t.Fatalf("expected node RF view for node 7, got nil")
	}
	if view.RssiDbm != -82 || view.SnrDb != -7.75 {
		t.Errorf("unexpected RF values: rssi=%d, snr=%v", view.RssiDbm, view.SnrDb)
	}
}

func TestHandleAlertMessage_WithMalformedRF_PreservesBusinessEvent(t *testing.T) {
	tracker := presence.NewRFTracker()
	mockEvtStore := &mockEventStore{}
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, mockEvtStore, nil, nil)
	subscriber.SetRFTracker(tracker)

	// Malformed snr_db (string instead of number)
	payload := `{
		"schema_version": "1.0-draft",
		"event_id": "gw01:550e8400-e29b-41d4-a716-446655440000:44",
		"gateway_id": "gw01",
		"gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
		"event_seq": "44",
		"observed_at": "2026-11-14T08:00:00Z",
		"observed_time_source": "gateway_utc",
		"radio_rx_monotonic_us": "123456789",
		"buffered": false,
		"node_id": 8,
		"superframe_seq": 101,
		"seq_num": 52,
		"schedule_version": 5,
		"severity": "P1_HIGH",
		"data": {
			"event_ref": 1001,
			"event_code": 1,
			"event_value": 1,
			"observed_at": "2026-11-14T08:00:00Z"
		},
		"radio_ack_sent": true,
		"rf": {
			"rssi_dbm": -82,
			"snr_db": "not-a-number",
			"channel_idx": 3,
			"rx_monotonic_us": "123456789",
			"gateway_epoch": "550e8400-e29b-41d4-a716-446655440000",
			"sample_seq": "1008"
		}
	}`
	msg := &mockMessage{
		topic:   "iot/v1/gw/gw01/uplink/alert",
		payload: []byte(payload),
	}
	subscriber.handleAlertMessage(nil, msg)

	mockEvtStore.mu.Lock()
	recorded := mockEvtStore.recorded
	mockEvtStore.mu.Unlock()

	// Business event MUST still be recorded!
	if recorded == nil {
		t.Fatalf("expected alert event to still be recorded even when RF block is malformed")
	}
	if recorded.NodeID != 8 {
		t.Errorf("expected node_id 8, got %d", recorded.NodeID)
	}

	// RF record should NOT have been created due to malformed snr_db
	if view := tracker.GetNodeRFView("gw01", 8); view != nil {
		t.Errorf("expected nil RF view for node 8 with malformed SNR, got %+v", view)
	}
}

type orderCheckingEventStore struct {
	mockEventStore
	rfViewAtRecord *presence.NodeRFView
	tracker        *presence.RFTracker
}

func (m *orderCheckingEventStore) RecordEvent(ctx context.Context, event *domain.Event) (*storage.EventRecordResult, error) {
	res, err := m.mockEventStore.RecordEvent(ctx, event)
	m.mu.Lock()
	if m.tracker != nil {
		m.rfViewAtRecord = m.tracker.GetNodeRFView(event.GatewayID, int(event.NodeID))
	}
	m.mu.Unlock()
	return res, err
}

type orderCheckingHub struct {
	mockHub
	mu                sync.Mutex
	rfViewAtBroadcast *presence.NodeRFView
	broadcastCount    int
	tracker           *presence.RFTracker
}

func (m *orderCheckingHub) BroadcastAlert(ctx context.Context, payload realtime.AlertTriggeredPayload) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.broadcastCount++
	if m.tracker != nil {
		m.rfViewAtBroadcast = m.tracker.GetNodeRFView(payload.GatewayID, int(payload.NodeID))
	}
	return nil
}

func TestHandleAlertMessage_Ordering_RFMetricsIngestedBeforeBroadcastAndRecordEvent(t *testing.T) {
	tracker := presence.NewRFTracker()
	evtStore := &orderCheckingEventStore{tracker: tracker}
	hub := &orderCheckingHub{tracker: tracker}

	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, evtStore, nil, nil)
	subscriber.SetRFTracker(tracker)
	subscriber.hub = hub

	epoch := "550e8400-e29b-41d4-a716-446655440050"
	payload := fmt.Sprintf(`{
		"schema_version": "1.0-draft",
		"event_id": "gw-a:%s:10",
		"gateway_id": "gw-a",
		"gateway_epoch": "%s",
		"event_seq": "10",
		"observed_at": "2026-11-15T00:00:00Z",
		"observed_time_source": "gateway_utc",
		"radio_rx_monotonic_us": "123456789",
		"buffered": false,
		"node_id": 3,
		"superframe_seq": 1,
		"seq_num": 1,
		"schedule_version": 1,
		"severity": "P3_NORMAL",
		"data": {"event_ref": 10, "event_code": 1, "event_value": 42},
		"radio_ack_sent": true,
		"rf": {
			"rssi_dbm": -68,
			"snr_db": 9.5,
			"channel_idx": 2,
			"rx_monotonic_us": "123456789",
			"gateway_epoch": "%s",
			"sample_seq": "10"
		}
	}`, epoch, epoch, epoch)

	msg := &mockMessage{
		topic:   "iot/v1/gw/gw-a/uplink/alert",
		payload: []byte(payload),
	}
	subscriber.handleAlertMessage(nil, msg)

	// Verify RecordEvent executed AFTER RFTracker was updated
	evtStore.mu.Lock()
	rfAtRecord := evtStore.rfViewAtRecord
	evtStore.mu.Unlock()

	if rfAtRecord == nil {
		t.Fatalf("expected RFTracker to already contain RF data when RecordEvent was invoked")
	}
	if rfAtRecord.RssiDbm != -68 || rfAtRecord.SnrDb != 9.5 {
		t.Errorf("unexpected RF snapshot at RecordEvent: %+v", rfAtRecord)
	}

	// Verify BroadcastAlert executed AFTER RFTracker was updated
	hub.mu.Lock()
	rfAtBroadcast := hub.rfViewAtBroadcast
	count := hub.broadcastCount
	hub.mu.Unlock()

	if count != 1 {
		t.Errorf("expected 1 BroadcastAlert, got %d", count)
	}
	if rfAtBroadcast == nil {
		t.Fatalf("expected RFTracker to already contain RF data when BroadcastAlert was invoked")
	}
	if rfAtBroadcast.RssiDbm != -68 || rfAtBroadcast.SnrDb != 9.5 {
		t.Errorf("unexpected RF snapshot at BroadcastAlert: %+v", rfAtBroadcast)
	}
}

func TestHandleAlertMessage_RebootEpochTransitionAndConvergenceWithDedicatedTopic(t *testing.T) {
	tracker := presence.NewRFTracker()
	mockEvtStore := &mockEventStore{}
	subscriber := NewGatewayStatusSubscriber("tcp://localhost:1883", nil, nil, mockEvtStore, nil, nil)
	subscriber.SetRFTracker(tracker)

	gw := "gw-a"
	nodeID := 3
	epoch1 := "550e8400-e29b-41d4-a716-446655440001"
	epoch2 := "550e8400-e29b-41d4-a716-446655440002"

	// 1. Alert in boot epoch 1 with high sequence 62 (pre-reboot state)
	alert1 := fmt.Sprintf(`{
		"schema_version": "1.0-draft",
		"event_id": "%s:%s:62",
		"gateway_id": "%s",
		"gateway_epoch": "%s",
		"event_seq": "62",
		"observed_at": "2026-11-14T16:38:51Z",
		"observed_time_source": "gateway_utc",
		"radio_rx_monotonic_us": "1000000",
		"buffered": false,
		"node_id": %d,
		"superframe_seq": 1,
		"seq_num": 1,
		"schedule_version": 1,
		"severity": "P3_NORMAL",
		"data": {"event_ref": 62, "event_code": 1, "event_value": 20},
		"radio_ack_sent": true,
		"rf": {
			"rssi_dbm": -20,
			"snr_db": 6.5,
			"channel_idx": 2,
			"rx_monotonic_us": "1000000",
			"gateway_epoch": "%s",
			"sample_seq": "62"
		}
	}`, gw, epoch1, gw, epoch1, nodeID, epoch1)

	subscriber.handleAlertMessage(nil, &mockMessage{topic: "iot/v1/gw/gw-a/uplink/alert", payload: []byte(alert1)})

	view1 := tracker.GetNodeRFView(gw, nodeID)
	if view1 == nil || view1.RssiDbm != -20 || view1.SnrDb != 6.5 {
		t.Fatalf("unexpected view1: %+v", view1)
	}

	// 2. Gateway reboots! New epoch2 arrives with reset sequence = 1, fresh RSSI/SNR
	alert2 := fmt.Sprintf(`{
		"schema_version": "1.0-draft",
		"event_id": "%s:%s:1",
		"gateway_id": "%s",
		"gateway_epoch": "%s",
		"event_seq": "1",
		"observed_at": "2026-11-15T00:00:00Z",
		"observed_time_source": "gateway_utc",
		"radio_rx_monotonic_us": "2000000",
		"buffered": false,
		"node_id": %d,
		"superframe_seq": 1,
		"seq_num": 1,
		"schedule_version": 1,
		"severity": "P3_NORMAL",
		"data": {"event_ref": 63, "event_code": 1, "event_value": 21},
		"radio_ack_sent": true,
		"rf": {
			"rssi_dbm": -75,
			"snr_db": 8.25,
			"channel_idx": 2,
			"rx_monotonic_us": "2000000",
			"gateway_epoch": "%s",
			"sample_seq": "1"
		}
	}`, gw, epoch2, gw, epoch2, nodeID, epoch2)

	subscriber.handleAlertMessage(nil, &mockMessage{topic: "iot/v1/gw/gw-a/uplink/alert", payload: []byte(alert2)})

	view2 := tracker.GetNodeRFView(gw, nodeID)
	if view2 == nil || view2.RssiDbm != -75 || view2.SnrDb != 8.25 {
		t.Fatalf("snapshot failed to update after reboot: %+v", view2)
	}

	// 3. Dedicated rf-metrics topic delivers same sample (epoch2, seq 1):
	// Must deduplicate cleanly and NOT corrupt or overwrite snapshot
	rfMetricsDup := fmt.Sprintf(`{
		"schema_version": "1.0-draft",
		"gateway_id": "%s",
		"gateway_epoch": "%s",
		"sample_seq": "1",
		"sample_monotonic_us": "2000000",
		"kind": "NODE_UPLINK",
		"node_id": %d,
		"rssi_dbm": -75,
		"snr_db": 8.25,
		"channel_idx": 2,
		"source": "UP_EVENT",
		"validation": "VERIFIED"
	}`, gw, epoch2, nodeID)

	subscriber.handleRFMetricsMessage(nil, &mockMessage{topic: "iot/v1/gw/gw-a/uplink/rf-metrics", payload: []byte(rfMetricsDup)})

	viewAfterDup := tracker.GetNodeRFView(gw, nodeID)
	if viewAfterDup.RssiDbm != -75 || viewAfterDup.SnrDb != 8.25 {
		t.Fatalf("duplicate sample corrupted snapshot: %+v", viewAfterDup)
	}

	// 4. Late alert from retired epoch1 (seq 63): MUST BE REJECTED!
	alertLate := fmt.Sprintf(`{
		"schema_version": "1.0-draft",
		"event_id": "%s:%s:63",
		"gateway_id": "%s",
		"gateway_epoch": "%s",
		"event_seq": "63",
		"observed_at": "2026-11-14T16:39:00Z",
		"observed_time_source": "gateway_utc",
		"radio_rx_monotonic_us": "1050000",
		"buffered": false,
		"node_id": %d,
		"superframe_seq": 1,
		"seq_num": 1,
		"schedule_version": 1,
		"severity": "P3_NORMAL",
		"data": {"event_ref": 63, "event_code": 1, "event_value": 20},
		"radio_ack_sent": true,
		"rf": {
			"rssi_dbm": -20,
			"snr_db": 6.5,
			"channel_idx": 2,
			"rx_monotonic_us": "1050000",
			"gateway_epoch": "%s",
			"sample_seq": "63"
		}
	}`, gw, epoch1, gw, epoch1, nodeID, epoch1)

	subscriber.handleAlertMessage(nil, &mockMessage{topic: "iot/v1/gw/gw-a/uplink/alert", payload: []byte(alertLate)})

	viewFinal := tracker.GetNodeRFView(gw, nodeID)
	if viewFinal.RssiDbm != -75 || viewFinal.SnrDb != 8.25 {
		t.Fatalf("snapshot was corrupted by late sample from retired epoch1: %+v", viewFinal)
	}
}
