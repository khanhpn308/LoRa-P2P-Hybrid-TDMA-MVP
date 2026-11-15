package presence_test

import (
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/presence"
)

func TestRFTracker_NodeUplink_BasicAndPrecision(t *testing.T) {
	tracker := presence.NewRFTracker()
	gwEpoch := "550e8400-e29b-41d4-a716-446655440000"
	chIdx := 4

	// Accept initial sample with -7.75 dB SNR
	ok := tracker.UpdateNodeRF("gw01", 10, -85, -7.75, &chIdx, "UP_EVENT", "VERIFIED", gwEpoch, 100, 1000000, 50)
	if !ok {
		t.Fatalf("expected sample to be accepted")
	}

	view := tracker.GetNodeRFView("gw01", 10)
	if view == nil {
		t.Fatalf("expected non-nil view")
	}
	if view.RssiDbm != -85 {
		t.Errorf("expected RSSI -85, got %d", view.RssiDbm)
	}
	if view.SnrDb != -7.75 {
		t.Errorf("expected SNR -7.75, got %f", view.SnrDb)
	}
	if view.ChannelIdx == nil || *view.ChannelIdx != 4 {
		t.Errorf("expected channelIdx 4, got %v", view.ChannelIdx)
	}
	if view.Source != "UP_EVENT" {
		t.Errorf("expected source UP_EVENT, got %s", view.Source)
	}
	if view.RfStale {
		t.Errorf("expected sample to be fresh, got stale")
	}

	// Also check GetLatestNodeRFView
	latest := tracker.GetLatestNodeRFView(10)
	if latest == nil || latest.SnrDb != -7.75 {
		t.Errorf("expected latest view to return -7.75 dB SNR, got %v", latest)
	}

	// Accept zero SNR
	ok = tracker.UpdateNodeRF("gw01", 10, -70, 0.0, &chIdx, "UP_HEARTBEAT_ACK", "VERIFIED", gwEpoch, 101, 1005000, 10)
	if !ok {
		t.Fatalf("expected sample with 0.0 dB SNR to be accepted")
	}
	view = tracker.GetNodeRFView("gw01", 10)
	if view == nil || view.SnrDb != 0.0 {
		t.Errorf("expected SNR 0.0, got %v", view)
	}
	if view.RssiDbm != -70 {
		t.Errorf("expected RSSI -70, got %d", view.RssiDbm)
	}
}

func TestRFTracker_MonotonicSequencingAndDedup(t *testing.T) {
	tracker := presence.NewRFTracker()
	epoch1 := "550e8400-e29b-41d4-a716-446655440001"

	// Sample 1
	if !tracker.UpdateNodeRF("gw01", 5, -80, 5.5, nil, "UP_EVENT", "VERIFIED", epoch1, 200, 2000000, 10) {
		t.Fatalf("expected sample 200 to be accepted")
	}

	// Duplicate sample with same sequence
	if tracker.UpdateNodeRF("gw01", 5, -99, 1.0, nil, "UP_EVENT", "VERIFIED", epoch1, 200, 2000000, 5) {
		t.Errorf("expected duplicate seq 200 to be rejected")
	}

	// Out-of-order older sample with lower sequence
	if tracker.UpdateNodeRF("gw01", 5, -99, 1.0, nil, "UP_EVENT", "VERIFIED", epoch1, 199, 1990000, 5) {
		t.Errorf("expected older seq 199 to be rejected")
	}

	// Verify state wasn't overwritten by rejected samples
	view := tracker.GetNodeRFView("gw01", 5)
	if view.RssiDbm != -80 || view.SnrDb != 5.5 {
		t.Errorf("state corrupted: %+v", view)
	}

	// Reboot epoch transition: new epoch accepted even with lower seq
	epoch2 := "550e8400-e29b-41d4-a716-446655440002"
	if !tracker.UpdateNodeRF("gw01", 5, -65, 8.0, nil, "UP_EVENT", "VERIFIED", epoch2, 1, 100000, 5) {
		t.Fatalf("expected new epoch to be accepted")
	}
	view = tracker.GetNodeRFView("gw01", 5)
	if view.RssiDbm != -65 || view.SnrDb != 8.0 {
		t.Errorf("expected updated state after epoch rollover: %+v", view)
	}
}

func TestRFTracker_InvalidBounds(t *testing.T) {
	tracker := presence.NewRFTracker()
	epoch := "550e8400-e29b-41d4-a716-446655440000"

	// Invalid node_id (0, 255)
	if tracker.UpdateNodeRF("gw01", 0, -80, 5.0, nil, "UP_EVENT", "VERIFIED", epoch, 1, 1, 0) {
		t.Errorf("expected node_id 0 to be rejected")
	}
	if tracker.UpdateNodeRF("gw01", 255, -80, 5.0, nil, "UP_EVENT", "VERIFIED", epoch, 1, 1, 0) {
		t.Errorf("expected node_id 255 to be rejected")
	}

	// Invalid channel_idx (> 10)
	invalidCh := 11
	if tracker.UpdateNodeRF("gw01", 1, -80, 5.0, &invalidCh, "UP_EVENT", "VERIFIED", epoch, 1, 1, 0) {
		t.Errorf("expected channel_idx 11 to be rejected")
	}

	// Invalid channel RF
	if tracker.UpdateChannelRF("gw01", 15, -100, "RX_IDLE", epoch, 1, 1, 0) {
		t.Errorf("expected channel_idx 15 to be rejected")
	}
	if tracker.UpdateChannelRF("", 0, -100, "RX_IDLE", epoch, 1, 1, 0) {
		t.Errorf("expected empty gateway_id to be rejected")
	}
}

func TestRFTracker_ChannelRF(t *testing.T) {
	tracker := presence.NewRFTracker()
	epoch := "550e8400-e29b-41d4-a716-446655440000"

	if !tracker.UpdateChannelRF("gw01", 2, -105, "RX_IDLE", epoch, 50, 500000, 100) {
		t.Fatalf("expected channel sample to be accepted")
	}

	view := tracker.GetChannelRFView("gw01", 2)
	if view == nil {
		t.Fatalf("expected non-nil channel view")
	}
	if view.ChannelRssiDbm != -105 {
		t.Errorf("expected RSSI -105, got %d", view.ChannelRssiDbm)
	}
	if view.SampleContext != "RX_IDLE" {
		t.Errorf("expected sample context RX_IDLE, got %s", view.SampleContext)
	}
	if view.ChannelRfStale {
		t.Errorf("expected channel sample to be fresh")
	}

	// Test getting latest channel view with channelIdx < 0
	latestView := tracker.GetChannelRFView("gw01", -1)
	if latestView == nil || latestView.ChannelIdx != 2 {
		t.Errorf("expected latest channel view on ch 2, got %v", latestView)
	}
}

func TestRFTracker_FreshnessAndStale(t *testing.T) {
	tracker := presence.NewRFTracker()
	tracker.SetFreshnessThresholds(50*time.Millisecond, 50*time.Millisecond)
	epoch := "550e8400-e29b-41d4-a716-446655440000"

	tracker.UpdateNodeRF("gw01", 7, -80, 4.0, nil, "UP_EVENT", "VERIFIED", epoch, 1, 1, 0)
	time.Sleep(70 * time.Millisecond)

	view := tracker.GetNodeRFView("gw01", 7)
	if view == nil {
		t.Fatalf("expected view")
	}
	if !view.RfStale {
		t.Errorf("expected sample to become stale after threshold, got fresh")
	}
	if view.RfAgeSeconds < 0 {
		t.Errorf("expected age >= 0, got %d", view.RfAgeSeconds)
	}
}

func TestRFTracker_RemovalAndClear(t *testing.T) {
	tracker := presence.NewRFTracker()
	epoch := "550e8400-e29b-41d4-a716-446655440000"

	tracker.UpdateNodeRF("gw01", 1, -80, 4.0, nil, "UP_EVENT", "VERIFIED", epoch, 1, 1, 0)
	tracker.UpdateNodeRF("gw01", 2, -85, 3.0, nil, "UP_EVENT", "VERIFIED", epoch, 1, 1, 0)
	tracker.UpdateChannelRF("gw01", 0, -100, "RX_IDLE", epoch, 1, 1, 0)

	tracker.RemoveNode(1)
	if tracker.GetNodeRFView("gw01", 1) != nil {
		t.Errorf("expected node 1 to be removed")
	}
	if tracker.GetNodeRFView("gw01", 2) == nil {
		t.Errorf("expected node 2 to remain")
	}

	tracker.RemoveGateway("gw01")
	if tracker.GetNodeRFView("gw01", 2) != nil {
		t.Errorf("expected node 2 under gw01 to be removed")
	}
	if tracker.GetChannelRFView("gw01", 0) != nil {
		t.Errorf("expected channel 0 under gw01 to be removed")
	}
}

func TestRFTracker_Concurrency(t *testing.T) {
	tracker := presence.NewRFTracker()
	epoch := "550e8400-e29b-41d4-a716-446655440000"

	var wg sync.WaitGroup
	workers := 10
	iterations := 100

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			for i := 0; i < iterations; i++ {
				nodeID := (i % 20) + 1
				seq := uint64(workerID*iterations + i + 1)
				tracker.UpdateNodeRF(
					fmt.Sprintf("gw%02d", workerID%3),
					nodeID,
					-80-(i%20),
					float64(i%10)-5.0,
					nil,
					"UP_EVENT",
					"VERIFIED",
					epoch,
					seq,
					uint64(i*1000),
					uint32(i%50),
				)
				_ = tracker.GetNodeRFView(fmt.Sprintf("gw%02d", workerID%3), nodeID)
				_ = tracker.GetLatestNodeRFView(nodeID)
			}
		}(w)
	}

	wg.Wait()
}

func TestRFTracker_RebootEpochTransitionAndRetiredRejection(t *testing.T) {
	tracker := presence.NewRFTracker()
	gw := "gw-a"
	nodeID := 3

	epochA := "550e8400-e29b-41d4-a716-446655440001"
	epochB := "550e8400-e29b-41d4-a716-446655440002"
	epochC := "550e8400-e29b-41d4-a716-446655440003"

	// 1. Initial boot with epochA: samples 1 to 62
	for seq := uint64(1); seq <= 62; seq++ {
		ok, reason := tracker.UpdateNodeRFWithReason(
			gw, nodeID, -20, 6.5, nil, "UP_EVENT", "VERIFIED", epochA, seq, seq*1000, 0,
		)
		if !ok {
			t.Fatalf("failed to ingest sample seq %d: reason=%s", seq, reason)
		}
	}

	viewA := tracker.GetNodeRFView(gw, nodeID)
	if viewA == nil || viewA.RssiDbm != -20 || viewA.SnrDb != 6.5 {
		t.Fatalf("unexpected snapshot view A: %+v", viewA)
	}
	if tracker.GetCurrentEpoch(gw) != epochA {
		t.Fatalf("expected active epoch to be epochA, got %s", tracker.GetCurrentEpoch(gw))
	}

	// 2. Gateway reboots: epochB arrives with reset sequence = 1, fresh RSSI/SNR
	ok, reason := tracker.UpdateNodeRFWithReason(
		gw, nodeID, -72, 9.25, nil, "UP_EVENT", "VERIFIED", epochB, 1, 1000, 0,
	)
	if !ok || reason != "ACCEPTED_NEW_EPOCH" {
		t.Fatalf("expected epochB with seq 1 to be accepted as new epoch, got ok=%v reason=%s", ok, reason)
	}

	viewB := tracker.GetNodeRFView(gw, nodeID)
	if viewB == nil || viewB.RssiDbm != -72 || viewB.SnrDb != 9.25 {
		t.Fatalf("snapshot not updated to epochB: %+v", viewB)
	}
	if tracker.GetCurrentEpoch(gw) != epochB {
		t.Fatalf("expected active epoch to be epochB, got %s", tracker.GetCurrentEpoch(gw))
	}

	// 3. Late delayed packet from retired epochA (high seq 63) arrives: MUST BE REJECTED
	ok, reason = tracker.UpdateNodeRFWithReason(
		gw, nodeID, -20, 6.5, nil, "UP_EVENT", "VERIFIED", epochA, 63, 63000, 0,
	)
	if ok || reason != "RETIRED_EPOCH" {
		t.Fatalf("expected late packet from retired epochA to be rejected, got ok=%v reason=%s", ok, reason)
	}

	// Verify snapshot is NOT overwritten
	viewCurrent := tracker.GetNodeRFView(gw, nodeID)
	if viewCurrent.RssiDbm != -72 || viewCurrent.SnrDb != 9.25 {
		t.Fatalf("snapshot was corrupted by retired epochA: %+v", viewCurrent)
	}

	// 4. Duplicate sequence in epochB (seq 1 again): MUST BE REJECTED as STALE_OR_DUPLICATE_SEQUENCE
	ok, reason = tracker.UpdateNodeRFWithReason(
		gw, nodeID, -99, 1.0, nil, "UP_EVENT", "VERIFIED", epochB, 1, 1000, 0,
	)
	if ok || reason != "STALE_OR_DUPLICATE_SEQUENCE" {
		t.Fatalf("expected duplicate seq 1 in epochB to be rejected, got ok=%v reason=%s", ok, reason)
	}

	// 5. Subsequent monotonic samples in epochB (seq 2, 3): MUST BE ACCEPTED
	ok, reason = tracker.UpdateNodeRFWithReason(
		gw, nodeID, -68, 10.0, nil, "UP_EVENT", "VERIFIED", epochB, 2, 2000, 0,
	)
	if !ok || reason != "ACCEPTED_MONOTONIC" {
		t.Fatalf("expected monotonic seq 2 in epochB to be accepted, got ok=%v reason=%s", ok, reason)
	}

	// 6. Another reboot: epochC arrives with seq 1
	ok, reason = tracker.UpdateNodeRFWithReason(
		gw, nodeID, -60, 11.5, nil, "UP_EVENT", "VERIFIED", epochC, 1, 1000, 0,
	)
	if !ok || reason != "ACCEPTED_NEW_EPOCH" {
		t.Fatalf("expected epochC to be accepted, got ok=%v reason=%s", ok, reason)
	}

	// Now BOTH epochA and epochB are retired
	retired := tracker.GetRetiredEpochs(gw)
	if len(retired) != 2 || retired[0] != epochA || retired[1] != epochB {
		t.Fatalf("unexpected retired epochs list: %+v", retired)
	}

	// Both epochA and epochB must be rejected
	if ok, _ := tracker.UpdateNodeRFWithReason(gw, nodeID, -10, 0, nil, "UP_EVENT", "VERIFIED", epochA, 999, 999, 0); ok {
		t.Fatalf("epochA should be rejected as retired")
	}
	if ok, _ := tracker.UpdateNodeRFWithReason(gw, nodeID, -10, 0, nil, "UP_EVENT", "VERIFIED", epochB, 999, 999, 0); ok {
		t.Fatalf("epochB should be rejected as retired")
	}
}

func TestRFTracker_BoundedRetiredEpochs(t *testing.T) {
	tracker := presence.NewRFTracker()
	gw := "gw-bounded"

	// Transition through 25 epochs (exceeds MaxRetiredEpochsPerGateway = 16)
	for i := 1; i <= 25; i++ {
		epoch := fmt.Sprintf("550e8400-e29b-41d4-a716-%012d", i)
		ok, _ := tracker.UpdateNodeRFWithReason(gw, 1, -80, 5.0, nil, "UP_EVENT", "VERIFIED", epoch, 1, 1000, 0)
		if !ok {
			t.Fatalf("failed at epoch %d", i)
		}
	}

	retired := tracker.GetRetiredEpochs(gw)
	if len(retired) > 16 {
		t.Fatalf("retired epochs exceeded max bound 16: got %d", len(retired))
	}
	if len(retired) != 16 {
		t.Fatalf("expected exactly 16 retired epochs, got %d", len(retired))
	}
	// Oldest retained epoch should be 9 (25 - 1 - 15 = 9)
	expectedOldest := fmt.Sprintf("550e8400-e29b-41d4-a716-%012d", 9)
	if retired[0] != expectedOldest {
		t.Fatalf("expected oldest retained epoch %s, got %s", expectedOldest, retired[0])
	}
}

func TestRFTracker_ChannelRF_EpochTransitionAndRetiredRejection(t *testing.T) {
	tracker := presence.NewRFTracker()
	gw := "gw-channel"
	ch := 3

	epochA := "550e8400-e29b-41d4-a716-446655440010"
	epochB := "550e8400-e29b-41d4-a716-446655440020"

	// Epoch A sample
	ok, reason := tracker.UpdateChannelRFWithReason(gw, ch, -105, "RX_IDLE", epochA, 10, 10000, 0)
	if !ok || reason != "ACCEPTED_FIRST_SAMPLE" {
		t.Fatalf("expected first sample accepted, got ok=%v reason=%s", ok, reason)
	}

	// Reboot: Epoch B sample with reset seq = 1
	ok, reason = tracker.UpdateChannelRFWithReason(gw, ch, -112, "RX_ACTIVE", epochB, 1, 1000, 0)
	if !ok || reason != "ACCEPTED_NEW_EPOCH" {
		t.Fatalf("expected new epoch accepted, got ok=%v reason=%s", ok, reason)
	}

	// Retired Epoch A sample rejected
	ok, reason = tracker.UpdateChannelRFWithReason(gw, ch, -90, "RX_IDLE", epochA, 99, 99000, 0)
	if ok || reason != "RETIRED_EPOCH" {
		t.Fatalf("expected retired epoch rejected, got ok=%v reason=%s", ok, reason)
	}

	view := tracker.GetChannelRFView(gw, ch)
	if view == nil || view.ChannelRssiDbm != -112 || view.SampleContext != "RX_ACTIVE" {
		t.Fatalf("channel view corrupted by retired epoch: %+v", view)
	}
}
