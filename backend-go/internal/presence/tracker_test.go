package presence

import (
	"testing"
)

func TestTracker_GatewayPresence(t *testing.T) {
	tracker := NewTracker()

	if tracker.IsGatewayOnline("gw-a") {
		t.Errorf("expected gw-a to be offline initially")
	}

	tracker.SetGatewayStatus("gw-a", true)
	if !tracker.IsGatewayOnline("gw-a") {
		t.Errorf("expected gw-a to be online")
	}

	gws := tracker.GetAllOnlineGateways()
	if len(gws) != 1 || gws[0] != "gw-a" {
		t.Errorf("expected [gw-a], got %v", gws)
	}

	tracker.SetGatewayStatus("gw-a", false)
	if tracker.IsGatewayOnline("gw-a") {
		t.Errorf("expected gw-a to be offline after SetGatewayStatus(false)")
	}
}

func TestTracker_NodePresence(t *testing.T) {
	tracker := NewTracker()

	if tracker.IsNodeOnline(1) {
		t.Errorf("expected node 1 to be offline initially")
	}

	tracker.SetNodeStatus(1, true)
	if !tracker.IsNodeOnline(1) {
		t.Errorf("expected node 1 to be online")
	}

	nodes := tracker.GetAllOnlineNodes()
	if len(nodes) != 1 || nodes[0] != 1 {
		t.Errorf("expected [1], got %v", nodes)
	}

	tracker.SetNodeStatus(1, false)
	if tracker.IsNodeOnline(1) {
		t.Errorf("expected node 1 to be offline after SetNodeStatus(false)")
	}
}

func TestTracker_ApplyNodeBitmap(t *testing.T) {
	tracker := NewTracker()

	// Bitmap for 8 nodes: node 1, 3, 5 are online (binary: 00010101 = 0x15)
	bitmap := []byte{0x15}
	tracker.ApplyNodeBitmap("gw-a", 8, bitmap)

	if !tracker.IsNodeOnline(1) {
		t.Errorf("expected node 1 to be online")
	}
	if tracker.IsNodeOnline(2) {
		t.Errorf("expected node 2 to be offline")
	}
	if !tracker.IsNodeOnline(3) {
		t.Errorf("expected node 3 to be online")
	}
	if tracker.IsNodeOnline(4) {
		t.Errorf("expected node 4 to be offline")
	}
	if !tracker.IsNodeOnline(5) {
		t.Errorf("expected node 5 to be online")
	}
	if tracker.IsNodeOnline(6) {
		t.Errorf("expected node 6 to be offline")
	}
}

func TestTracker_GatewayHeartbeatAndTimeout(t *testing.T) {
	tracker := NewTracker()

	tracker.UpdateGatewayHeartbeat("gw-a", 0x01, -65, 3600, 180000, 42)

	if !tracker.IsGatewayOnline("gw-a") {
		t.Errorf("expected gw-a to be online after heartbeat")
	}

	tel := tracker.GetGatewayTelemetry("gw-a")
	if tel == nil || !tel.LoraOK || tel.WifiRSSI != -65 || tel.UptimeS != 3600 {
		t.Errorf("unexpected telemetry: %+v", tel)
	}

	// Immediate timeout check with 1 hour threshold should not timeout
	timedOut := tracker.CheckGatewayTimeouts(3600 * 1000000000)
	if len(timedOut) > 0 {
		t.Errorf("expected no timed out gateways, got %v", timedOut)
	}
}
