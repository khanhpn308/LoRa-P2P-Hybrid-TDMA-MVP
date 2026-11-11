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
}

func (m *mockJoinReqStorage) IsDeviceRegistered(ctx context.Context, mac string) (bool, error) {
	m.isRegisteredCalled = true
	m.lastCheckedMAC = mac
	return m.isRegistered, m.checkErr
}

func (m *mockJoinReqStorage) CreateOrUpdatePendingRequest(ctx context.Context, req *domain.DeviceJoinRequest) (*domain.DeviceJoinRequest, error) {
	if m.createErr != nil {
		return nil, m.createErr
	}
	m.createdReq = req
	return &domain.DeviceJoinRequest{
		ID:          101,
		DeviceMAC:   req.DeviceMAC,
		GatewayID:   req.GatewayID,
		RSSI:        req.RSSI,
		SNR:         req.SNR,
		RawFrameHex: req.RawFrameHex,
		Status:      "PENDING",
		CreatedAt:   time.Now().UTC(),
		UpdatedAt:   time.Now().UTC(),
	}, nil
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
