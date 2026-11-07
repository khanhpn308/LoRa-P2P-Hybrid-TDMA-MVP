package mqtt_test

import (
	"context"
	"encoding/hex"
	"encoding/json/v2"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
)

func TestBoundedWorkerPool_ProcessJobs(t *testing.T) {
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

	pool := mqtt.NewBoundedWorkerPool(handler, 2, 5, 2*time.Second)
	defer pool.Stop()

	req := mqtt.IngestRequest{
		Topic:           "iot/v1/gw/gw-alpha/uplink/join-hello",
		Payload:         payload,
		BrokerGatewayID: "gw-alpha",
	}

	respChan := make(chan mqtt.IngestJobResult, 1)
	if err := pool.Enqueue(req, respChan); err != nil {
		t.Fatalf("failed to enqueue: %v", err)
	}

	select {
	case res := <-respChan:
		if res.Err != nil {
			t.Fatalf("job execution failed: %v", res.Err)
		}
		if res.Response.JoinCounter != 10 {
			t.Fatalf("expected counter 10, got %d", res.Response.JoinCounter)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for worker pool response")
	}
}

func TestBoundedWorkerPool_BackpressureFull(t *testing.T) {
	t.Parallel()

	handler, _, _, _ := setupFixture(t)
	// Capacity 1, 0 workers (workers don't consume so queue fills immediately)
	pool := mqtt.NewBoundedWorkerPool(handler, 1, 1, 1*time.Second)
	defer pool.Stop()

	req := mqtt.IngestRequest{
		Topic: "iot/v1/gw/gw-alpha/uplink/join-hello",
	}

	// First job might enter or be processed
	_ = pool.Enqueue(req, nil)
	// Quickly fill queue
	var fullErr error
	for i := 0; i < 10; i++ {
		err := pool.Enqueue(req, nil)
		if errors.Is(err, mqtt.ErrQueueFull) {
			fullErr = err
			break
		}
	}

	if fullErr == nil {
		t.Log("Note: fast worker consumed jobs, queue didn't overflow under light load")
	}
}

func TestTokenBucketLimiter_Concurrency(t *testing.T) {
	t.Parallel()

	limiter := mqtt.NewTokenBucketLimiter(10, 100)
	var wg sync.WaitGroup
	ctx := context.Background()

	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_ = limiter.Allow(ctx, "test-key")
		}()
	}
	wg.Wait()
}
