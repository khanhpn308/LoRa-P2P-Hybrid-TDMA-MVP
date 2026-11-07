package mqtt_test

import (
	"context"
	"crypto/rand"
	"encoding/binary"
	"encoding/hex"
	"encoding/json/v2"
	"errors"
	"fmt"
	"sync"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockJoinRepo struct {
	mu           sync.Mutex
	devices      map[string]*storage.DeviceRecord
	transactions map[string]*storage.JoinHelloTxResult
	lastCounter  map[string]uint32
	storedHashes map[string][32]byte
}

func newMockJoinRepo() *mockJoinRepo {
	return &mockJoinRepo{
		devices:      make(map[string]*storage.DeviceRecord),
		transactions: make(map[string]*storage.JoinHelloTxResult),
		lastCounter:  make(map[string]uint32),
		storedHashes: make(map[string][32]byte),
	}
}

func (m *mockJoinRepo) GetActiveDevice(ctx context.Context, networkID uint32, mac [6]byte) (*storage.DeviceRecord, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	key := fmt.Sprintf("%d:%x", networkID, mac[:])
	d, ok := m.devices[key]
	if !ok {
		return nil, storage.ErrDeviceNotFound
	}
	if d.Status != "ACTIVE" {
		return nil, storage.ErrDeviceNotActive
	}
	res := *d
	return &res, nil
}

func (m *mockJoinRepo) RecordJoinHello(ctx context.Context, in *storage.JoinHelloTxInput) (*storage.JoinHelloTxResult, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	devKey := fmt.Sprintf("%d:%x", in.NetworkID, in.DeviceMAC[:])
	d, ok := m.devices[devKey]
	if !ok || d.Status != "ACTIVE" {
		return nil, storage.ErrDeviceNotActive
	}

	txKey := fmt.Sprintf("%s:%d:%d", devKey, in.Generation, in.JoinCounter)
	last := m.lastCounter[devKey]

	if in.JoinCounter <= last {
		storedHash, exists := m.storedHashes[txKey]
		if exists && storedHash == in.RawHelloSHA256 {
			return &storage.JoinHelloTxResult{
				TransactionID:      m.transactions[txKey].TransactionID,
				Status:             domain.StatusHelloAuthenticatedPendingGrant,
				IsIdempotentReplay: true,
				JoinCounter:        in.JoinCounter,
			}, nil
		}
		if exists {
			return nil, storage.ErrReplayDetected
		}
		return nil, storage.ErrStaleJoinCounter
	}

	m.lastCounter[devKey] = in.JoinCounter
	m.storedHashes[txKey] = in.RawHelloSHA256
	res := &storage.JoinHelloTxResult{
		TransactionID:      int64(len(m.transactions) + 1),
		Status:             domain.StatusHelloAuthenticatedPendingGrant,
		IsIdempotentReplay: false,
		JoinCounter:        in.JoinCounter,
	}
	m.transactions[txKey] = res
	return res, nil
}

func buildValidFrame(networkID uint32, gen uint16, mac [6]byte, targetGW uint8, counter uint32, kJoin [32]byte) ([]byte, error) {
	frame := make([]byte, 68)
	frame[0] = domain.VerTypeUpJoinHello
	copy(frame[1:7], mac[:])
	frame[7] = targetGW
	binary.BigEndian.PutUint32(frame[8:12], counter)
	for i := 12; i < 20; i++ {
		frame[i] = byte(i)
	}
	for i := 20; i < 52; i++ {
		frame[i] = byte(i)
	}

	kjReq, err := security.DeriveKJReq(networkID, mac, gen, kJoin)
	if err != nil {
		return nil, err
	}
	proof, err := security.ComputeHelloProof(networkID, frame[0:52], kjReq)
	if err != nil {
		return nil, err
	}
	copy(frame[52:68], proof[:])
	return frame, nil
}

func setupFixture(t *testing.T) (*mqtt.JoinHelloIngestHandler, *mockJoinRepo, [6]byte, [32]byte) {
	networkID := uint32(100)
	mac := [6]byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06}
	var kJoin [32]byte
	_, _ = rand.Read(kJoin[:])

	repo := newMockJoinRepo()
	devKey := fmt.Sprintf("%d:%x", networkID, mac[:])
	repo.devices[devKey] = &storage.DeviceRecord{
		NetworkID:        networkID,
		DeviceMAC:        mac,
		Status:           "ACTIVE",
		ActiveGeneration: 1,
		KJoinWrapped:     kJoin[:],
	}

	gwDir := mqtt.NewStaticGatewayDirectory(mqtt.GatewayInfo{
		GatewayID: "gw-alpha",
		NumericID: 1,
		NetworkID: networkID,
		IsActive:  true,
	})

	handler, err := mqtt.NewJoinHelloIngestHandler(mqtt.HandlerConfig{
		JoinRepo:   repo,
		GatewayDir: gwDir,
	})
	if err != nil {
		t.Fatalf("failed to create handler: %v", err)
	}

	return handler, repo, mac, kJoin
}

func TestJoinHelloIngestHandler_Success(t *testing.T) {
	t.Parallel()

	handler, _, mac, kJoin := setupFixture(t)
	rawFrame, err := buildValidFrame(100, 1, mac, 1, 10, kJoin)
	if err != nil {
		t.Fatalf("failed to build frame: %v", err)
	}

	obsAt := "2026-11-07T12:00:00.000Z"
	env := mqtt.JoinHelloEnvelope{
		SchemaVersion:      mqtt.SchemaVersionJoinHello,
		EventID:            "gw-alpha:12345678-1234-1234-1234-123456789abc:1",
		GatewayID:          "gw-alpha",
		GatewayEpoch:       "12345678-1234-1234-1234-123456789abc",
		EventSeq:           "1",
		ObservedAt:         &obsAt,
		ObservedTimeSource: mqtt.TimeSourceGatewayUTC,
		RadioRxMonotonicUS: "12345678",
		Buffered:           false,
		TargetGWID:         1,
		RawFrameHex:        hex.EncodeToString(rawFrame),
		RSSI:               -75,
		SNR:                8.2,
	}

	payload, err := json.Marshal(env)
	if err != nil {
		t.Fatalf("failed to marshal envelope: %v", err)
	}

	req := mqtt.IngestRequest{
		Topic:           "iot/v1/gw/gw-alpha/uplink/join-hello",
		Payload:         payload,
		BrokerGatewayID: "gw-alpha",
	}

	resp, err := handler.Handle(context.Background(), req)
	if err != nil {
		t.Fatalf("expected successful ingestion, got: %v", err)
	}

	if resp.Status != domain.StatusHelloAuthenticatedPendingGrant {
		t.Fatalf("unexpected status: %s", resp.Status)
	}
	if resp.IsIdempotentReplay {
		t.Fatal("expected first attempt, not idempotent replay")
	}
	if resp.JoinCounter != 10 {
		t.Fatalf("expected counter 10, got %d", resp.JoinCounter)
	}
	if resp.DeviceMAC != mac {
		t.Fatalf("MAC mismatch: %+v", resp.DeviceMAC)
	}

	// 2. Retransmission test: byte-identical retransmission must return IsIdempotentReplay = true
	resp2, err := handler.Handle(context.Background(), req)
	if err != nil {
		t.Fatalf("expected successful idempotent retransmission, got: %v", err)
	}
	if !resp2.IsIdempotentReplay {
		t.Fatal("expected IsIdempotentReplay = true on duplicate")
	}
	if resp2.TransactionID != resp.TransactionID {
		t.Fatalf("transaction ID mismatch: %d vs %d", resp2.TransactionID, resp.TransactionID)
	}
}

func TestJoinHelloIngestHandler_IdentityMismatch(t *testing.T) {
	t.Parallel()

	handler, _, mac, kJoin := setupFixture(t)
	rawFrame, _ := buildValidFrame(100, 1, mac, 1, 10, kJoin)

	obsAt := "2026-11-07T12:00:00Z"
	env := mqtt.JoinHelloEnvelope{
		SchemaVersion:      mqtt.SchemaVersionJoinHello,
		EventID:            "gw-alpha:12345678-1234-1234-1234-123456789abc:1",
		GatewayID:          "gw-alpha",
		GatewayEpoch:       "12345678-1234-1234-1234-123456789abc",
		EventSeq:           "1",
		ObservedAt:         &obsAt,
		ObservedTimeSource: mqtt.TimeSourceGatewayUTC,
		RadioRxMonotonicUS: "100",
		Buffered:           false,
		TargetGWID:         1,
		RawFrameHex:        hex.EncodeToString(rawFrame),
		RSSI:               -70,
		SNR:                9.0,
	}
	payload, _ := json.Marshal(env)

	// Broker identity mismatch
	req := mqtt.IngestRequest{
		Topic:           "iot/v1/gw/gw-alpha/uplink/join-hello",
		Payload:         payload,
		BrokerGatewayID: "gw-spoofed",
	}
	_, err := handler.Handle(context.Background(), req)
	if !errors.Is(err, mqtt.ErrIdentityMismatch) {
		t.Fatalf("expected ErrIdentityMismatch for broker spoofing, got: %v", err)
	}

	// Payload gateway_id mismatch
	env.GatewayID = "gw-beta"
	env.EventID = "gw-beta:12345678-1234-1234-1234-123456789abc:1"
	payload2, _ := json.Marshal(env)
	req2 := mqtt.IngestRequest{
		Topic:           "iot/v1/gw/gw-alpha/uplink/join-hello",
		Payload:         payload2,
		BrokerGatewayID: "gw-alpha",
	}
	_, err2 := handler.Handle(context.Background(), req2)
	if !errors.Is(err2, mqtt.ErrIdentityMismatch) {
		t.Fatalf("expected ErrIdentityMismatch for payload gateway_id mismatch, got: %v", err2)
	}
}

func TestJoinHelloIngestHandler_TargetGWMismatch(t *testing.T) {
	t.Parallel()

	handler, _, mac, kJoin := setupFixture(t)
	// Frame targeted to GW 2, but gateway gw-alpha is numeric ID 1
	rawFrame, _ := buildValidFrame(100, 1, mac, 2, 10, kJoin)

	obsAt := "2026-11-07T12:00:00Z"
	env := mqtt.JoinHelloEnvelope{
		SchemaVersion:      mqtt.SchemaVersionJoinHello,
		EventID:            "gw-alpha:12345678-1234-1234-1234-123456789abc:1",
		GatewayID:          "gw-alpha",
		GatewayEpoch:       "12345678-1234-1234-1234-123456789abc",
		EventSeq:           "1",
		ObservedAt:         &obsAt,
		ObservedTimeSource: mqtt.TimeSourceGatewayUTC,
		RadioRxMonotonicUS: "100",
		Buffered:           false,
		TargetGWID:         2,
		RawFrameHex:        hex.EncodeToString(rawFrame),
		RSSI:               -70,
		SNR:                9.0,
	}
	payload, _ := json.Marshal(env)

	req := mqtt.IngestRequest{
		Topic:           "iot/v1/gw/gw-alpha/uplink/join-hello",
		Payload:         payload,
		BrokerGatewayID: "gw-alpha",
	}

	_, err := handler.Handle(context.Background(), req)
	if !errors.Is(err, mqtt.ErrTargetGWMismatch) {
		t.Fatalf("expected ErrTargetGWMismatch, got: %v", err)
	}
}

func TestJoinHelloIngestHandler_AuthenticationFailure(t *testing.T) {
	t.Parallel()

	handler, _, mac, kJoin := setupFixture(t)
	rawFrame, _ := buildValidFrame(100, 1, mac, 1, 10, kJoin)
	// Tamper proof (last byte)
	rawFrame[67] ^= 0xFF

	obsAt := "2026-11-07T12:00:00Z"
	env := mqtt.JoinHelloEnvelope{
		SchemaVersion:      mqtt.SchemaVersionJoinHello,
		EventID:            "gw-alpha:12345678-1234-1234-1234-123456789abc:1",
		GatewayID:          "gw-alpha",
		GatewayEpoch:       "12345678-1234-1234-1234-123456789abc",
		EventSeq:           "1",
		ObservedAt:         &obsAt,
		ObservedTimeSource: mqtt.TimeSourceGatewayUTC,
		RadioRxMonotonicUS: "100",
		Buffered:           false,
		TargetGWID:         1,
		RawFrameHex:        hex.EncodeToString(rawFrame),
		RSSI:               -70,
		SNR:                9.0,
	}
	payload, _ := json.Marshal(env)

	req := mqtt.IngestRequest{
		Topic:           "iot/v1/gw/gw-alpha/uplink/join-hello",
		Payload:         payload,
		BrokerGatewayID: "gw-alpha",
	}

	_, err := handler.Handle(context.Background(), req)
	if !errors.Is(err, mqtt.ErrAuthenticationFailed) {
		t.Fatalf("expected ErrAuthenticationFailed on tampered proof, got: %v", err)
	}
}

func TestJoinHelloIngestHandler_ConflictingReplayAttack(t *testing.T) {
	t.Parallel()

	handler, _, mac, kJoin := setupFixture(t)
	rawFrame1, _ := buildValidFrame(100, 1, mac, 1, 20, kJoin)

	obsAt := "2026-11-07T12:00:00Z"
	env1 := mqtt.JoinHelloEnvelope{
		SchemaVersion:      mqtt.SchemaVersionJoinHello,
		EventID:            "gw-alpha:12345678-1234-1234-1234-123456789abc:1",
		GatewayID:          "gw-alpha",
		GatewayEpoch:       "12345678-1234-1234-1234-123456789abc",
		EventSeq:           "1",
		ObservedAt:         &obsAt,
		ObservedTimeSource: mqtt.TimeSourceGatewayUTC,
		RadioRxMonotonicUS: "100",
		Buffered:           false,
		TargetGWID:         1,
		RawFrameHex:        hex.EncodeToString(rawFrame1),
		RSSI:               -70,
		SNR:                9.0,
	}
	p1, _ := json.Marshal(env1)
	req1 := mqtt.IngestRequest{Topic: "iot/v1/gw/gw-alpha/uplink/join-hello", Payload: p1, BrokerGatewayID: "gw-alpha"}

	_, err := handler.Handle(context.Background(), req1)
	if err != nil {
		t.Fatalf("first request failed: %v", err)
	}

	// Attacker replays with same counter 20 but modified node nonce
	rawFrame2, _ := buildValidFrame(100, 1, mac, 1, 20, kJoin)
	rawFrame2[12] ^= 0x55 // change nonce
	// recompute proof for this altered frame so crypto passes but hash differs
	kjReq, _ := security.DeriveKJReq(100, mac, 1, kJoin)
	proof2, _ := security.ComputeHelloProof(100, rawFrame2[0:52], kjReq)
	copy(rawFrame2[52:68], proof2[:])

	env2 := env1
	env2.EventSeq = "2"
	env2.EventID = "gw-alpha:12345678-1234-1234-1234-123456789abc:2"
	env2.RawFrameHex = hex.EncodeToString(rawFrame2)
	p2, _ := json.Marshal(env2)
	req2 := mqtt.IngestRequest{Topic: "iot/v1/gw/gw-alpha/uplink/join-hello", Payload: p2, BrokerGatewayID: "gw-alpha"}

	_, err = handler.Handle(context.Background(), req2)
	if !errors.Is(err, mqtt.ErrReplayDetected) {
		t.Fatalf("expected ErrReplayDetected on conflicting payload with same counter, got: %v", err)
	}
}

func TestJoinHelloIngestHandler_StaleCounterRollback(t *testing.T) {
	t.Parallel()

	handler, _, mac, kJoin := setupFixture(t)
	// First commit counter 50
	rawFrame50, _ := buildValidFrame(100, 1, mac, 1, 50, kJoin)
	obsAt := "2026-11-07T12:00:00Z"
	env := mqtt.JoinHelloEnvelope{
		SchemaVersion:      mqtt.SchemaVersionJoinHello,
		EventID:            "gw-alpha:12345678-1234-1234-1234-123456789abc:1",
		GatewayID:          "gw-alpha",
		GatewayEpoch:       "12345678-1234-1234-1234-123456789abc",
		EventSeq:           "1",
		ObservedAt:         &obsAt,
		ObservedTimeSource: mqtt.TimeSourceGatewayUTC,
		RadioRxMonotonicUS: "100",
		Buffered:           false,
		TargetGWID:         1,
		RawFrameHex:        hex.EncodeToString(rawFrame50),
		RSSI:               -70,
		SNR:                9.0,
	}
	p50, _ := json.Marshal(env)
	_, err := handler.Handle(context.Background(), mqtt.IngestRequest{Topic: "iot/v1/gw/gw-alpha/uplink/join-hello", Payload: p50, BrokerGatewayID: "gw-alpha"})
	if err != nil {
		t.Fatalf("commit counter 50 failed: %v", err)
	}

	// Now try to send counter 20 (< 50, never before seen)
	rawFrame20, _ := buildValidFrame(100, 1, mac, 1, 20, kJoin)
	env.EventSeq = "2"
	env.EventID = "gw-alpha:12345678-1234-1234-1234-123456789abc:2"
	env.RawFrameHex = hex.EncodeToString(rawFrame20)
	p20, _ := json.Marshal(env)

	_, err = handler.Handle(context.Background(), mqtt.IngestRequest{Topic: "iot/v1/gw/gw-alpha/uplink/join-hello", Payload: p20, BrokerGatewayID: "gw-alpha"})
	if !errors.Is(err, mqtt.ErrStaleJoinCounter) {
		t.Fatalf("expected ErrStaleJoinCounter on rolled back counter, got: %v", err)
	}
}

func TestJoinHelloIngestHandler_PayloadTooLarge(t *testing.T) {
	t.Parallel()

	handler, _, _, _ := setupFixture(t)
	oversized := make([]byte, 2049)
	req := mqtt.IngestRequest{
		Topic:           "iot/v1/gw/gw-alpha/uplink/join-hello",
		Payload:         oversized,
		BrokerGatewayID: "gw-alpha",
	}
	_, err := handler.Handle(context.Background(), req)
	if !errors.Is(err, mqtt.ErrPayloadTooLarge) {
		t.Fatalf("expected ErrPayloadTooLarge, got: %v", err)
	}
}
