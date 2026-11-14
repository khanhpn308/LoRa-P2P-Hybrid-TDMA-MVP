package presence

import (
	"sync"
	"time"
)

// GatewayTelemetry holds the latest ephemeral health metrics reported via heartbeat.
type GatewayTelemetry struct {
	Flags         uint8     `json:"flags"`
	LoraOK        bool      `json:"lora_ok"`
	WifiRSSI      int8      `json:"wifi_rssi"`
	UptimeS       uint32    `json:"uptime_s"`
	FreeHeapBytes uint32    `json:"free_heap_bytes"`
	RxEventsCount uint32    `json:"rx_events_count"`
	LastHeartbeat time.Time `json:"last_heartbeat"`
}

// Tracker manages ephemeral in-memory presence for Gateways and Nodes without disk writes.
type Tracker struct {
	mu           sync.RWMutex
	gateways     map[string]bool
	nodes        map[int]bool
	gwLastSeen   map[string]time.Time
	nodeLastSeen map[int]time.Time
	gwTelemetry  map[string]*GatewayTelemetry
	rfTracker    *RFTracker
}

// NewTracker creates an initialized thread-safe Presence Tracker.
func NewTracker() *Tracker {
	return &Tracker{
		gateways:     make(map[string]bool),
		nodes:        make(map[int]bool),
		gwLastSeen:   make(map[string]time.Time),
		nodeLastSeen: make(map[int]time.Time),
		gwTelemetry:  make(map[string]*GatewayTelemetry),
		rfTracker:    NewRFTracker(),
	}
}

// RF returns the associated RFTracker instance.
func (t *Tracker) RF() *RFTracker {
	if t == nil {
		return nil
	}
	t.mu.RLock()
	defer t.mu.RUnlock()
	return t.rfTracker
}

// SetRF sets a custom RFTracker instance.
func (t *Tracker) SetRF(rf *RFTracker) {
	if t == nil {
		return
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	t.rfTracker = rf
}

// SetGatewayStatus explicitly sets the in-memory presence of a gateway.
func (t *Tracker) SetGatewayStatus(gatewayID string, online bool) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if online {
		t.gateways[gatewayID] = true
		t.gwLastSeen[gatewayID] = time.Now().UTC()
	} else {
		delete(t.gateways, gatewayID)
		delete(t.gwLastSeen, gatewayID)
	}
}

// UpdateGatewayHeartbeat records a binary heartbeat from a gateway.
func (t *Tracker) UpdateGatewayHeartbeat(gatewayID string, flags uint8, wifiRSSI int8, uptimeS uint32, freeHeap uint32, rxEvents uint32) {
	t.mu.Lock()
	defer t.mu.Unlock()
	now := time.Now().UTC()
	t.gateways[gatewayID] = true
	t.gwLastSeen[gatewayID] = now
	t.gwTelemetry[gatewayID] = &GatewayTelemetry{
		Flags:         flags,
		LoraOK:        (flags & 0x01) != 0,
		WifiRSSI:      wifiRSSI,
		UptimeS:       uptimeS,
		FreeHeapBytes: freeHeap,
		RxEventsCount: rxEvents,
		LastHeartbeat: now,
	}
}

// GetGatewayTelemetry retrieves the latest heartbeat metrics for a gateway.
func (t *Tracker) GetGatewayTelemetry(gatewayID string) *GatewayTelemetry {
	t.mu.RLock()
	defer t.mu.RUnlock()
	if tel, ok := t.gwTelemetry[gatewayID]; ok {
		cpy := *tel
		return &cpy
	}
	return nil
}

// ApplyNodeBitmap updates node presence based on the binary bitmap reported by a gateway.
func (t *Tracker) ApplyNodeBitmap(gatewayID string, nodeCount int, bitmap []byte) {
	t.mu.Lock()
	defer t.mu.Unlock()
	now := time.Now().UTC()

	for i := 1; i <= nodeCount; i++ {
		byteIdx := (i - 1) / 8
		bitIdx := uint((i - 1) % 8)
		if byteIdx < len(bitmap) {
			isOnline := (bitmap[byteIdx] & (1 << bitIdx)) != 0
			if isOnline {
				t.nodes[i] = true
				t.nodeLastSeen[i] = now
			} else {
				delete(t.nodes, i)
				delete(t.nodeLastSeen, i)
			}
		}
	}
}

// CheckGatewayTimeouts finds gateways that have exceeded the heartbeat timeout and marks them offline.
func (t *Tracker) CheckGatewayTimeouts(timeout time.Duration) []string {
	t.mu.Lock()
	defer t.mu.Unlock()
	now := time.Now().UTC()
	var timedOut []string

	for gwID, online := range t.gateways {
		if online {
			last, ok := t.gwLastSeen[gwID]
			if !ok || now.Sub(last) > timeout {
				delete(t.gateways, gwID)
				delete(t.gwLastSeen, gwID)
				timedOut = append(timedOut, gwID)
			}
		}
	}
	return timedOut
}

// IsGatewayOnline checks if a gateway is currently online in memory.
func (t *Tracker) IsGatewayOnline(gatewayID string) bool {
	t.mu.RLock()
	defer t.mu.RUnlock()
	return t.gateways[gatewayID]
}

// SetNodeStatus explicitly sets the in-memory presence of a node.
func (t *Tracker) SetNodeStatus(nodeID int, online bool) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if online {
		t.nodes[nodeID] = true
		t.nodeLastSeen[nodeID] = time.Now().UTC()
	} else {
		delete(t.nodes, nodeID)
		delete(t.nodeLastSeen, nodeID)
	}
}

// IsNodeOnline checks if a node is currently online in memory.
func (t *Tracker) IsNodeOnline(nodeID int) bool {
	t.mu.RLock()
	defer t.mu.RUnlock()
	return t.nodes[nodeID]
}

// GetAllOnlineGateways returns a slice of all currently online gateway IDs.
func (t *Tracker) GetAllOnlineGateways() []string {
	t.mu.RLock()
	defer t.mu.RUnlock()
	out := make([]string, 0, len(t.gateways))
	for gwID, online := range t.gateways {
		if online {
			out = append(out, gwID)
		}
	}
	return out
}

// GetAllOnlineNodes returns a slice of all currently online node IDs.
func (t *Tracker) GetAllOnlineNodes() []int {
	t.mu.RLock()
	defer t.mu.RUnlock()
	out := make([]int, 0, len(t.nodes))
	for nID, online := range t.nodes {
		if online {
			out = append(out, nID)
		}
	}
	return out
}
