package mqtt

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log"
	"os"
	"strings"
	"testing"
	"time"

	paho "github.com/eclipse/paho.mqtt.golang"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
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
