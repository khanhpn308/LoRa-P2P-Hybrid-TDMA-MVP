package presence

import (
	"sync"
	"time"
)

const (
	// DefaultNodeRFFreshness is based on the 300s node health probe cadence.
	DefaultNodeRFFreshness = 300 * time.Second
	// DefaultChannelRFFreshness is based on the 30s gateway heartbeat cadence.
	DefaultChannelRFFreshness = 60 * time.Second
	// MaxGatewaysTracked limits memory to prevent unbounded map growth.
	MaxGatewaysTracked = 500
)

type nodeRFKey struct {
	gatewayID string
	nodeID    int
}

type channelRFKey struct {
	gatewayID  string
	channelIdx int
}

// NodeRFRecord stores the raw accepted in-memory RF measurement for a node.
type NodeRFRecord struct {
	GatewayID         string
	NodeID            int
	RssiDbm           int
	SnrDb             float64
	ChannelIdx        *int
	Source            string
	Validation        string
	GatewayEpoch      string
	SampleSeq         uint64
	SampleMonotonicUS uint64
	AgeMs             uint32
	ReceivedAt        time.Time
	MeasuredAt        time.Time
}

// ChannelRFRecord stores the raw accepted in-memory RF measurement for a gateway channel.
type ChannelRFRecord struct {
	GatewayID         string
	ChannelIdx        int
	ChannelRssiDbm    int
	SampleContext     string
	GatewayEpoch      string
	SampleSeq         uint64
	SampleMonotonicUS uint64
	AgeMs             uint32
	ReceivedAt        time.Time
	MeasuredAt        time.Time
}

// NodeRFView is the presentation DTO for a node's latest RF signal quality.
type NodeRFView struct {
	RssiDbm      int
	SnrDb        float64
	ChannelIdx   *int
	Source       string
	Validation   string
	MeasuredAt   time.Time
	LastRfAt     string
	RfAgeSeconds int
	RfStale      bool
}

// ChannelRFView is the presentation DTO for a gateway's channel energy state.
type ChannelRFView struct {
	ChannelIdx          int
	ChannelRssiDbm      int
	SampleContext       string
	MeasuredAt          time.Time
	ChannelRfAt         string
	ChannelRfAgeSeconds int
	ChannelRfStale      bool
}

// RFTracker manages ephemeral, bounded, concurrency-safe in-memory RF snapshots.
// It enforces monotonic sequence ordering per (gateway_epoch), handles reboot epoch transitions,
// deduplicates QoS1/WAL replays, and tracks age/freshness without disk writes or altering presence liveness.
type RFTracker struct {
	mu                        sync.RWMutex
	nodeSnapshots             map[nodeRFKey]*NodeRFRecord
	channelSnapshots          map[channelRFKey]*ChannelRFRecord
	gatewaysSeen              map[string]time.Time
	nodeFreshnessThreshold    time.Duration
	channelFreshnessThreshold time.Duration
}

// NewRFTracker constructs an initialized RFTracker.
func NewRFTracker() *RFTracker {
	return &RFTracker{
		nodeSnapshots:             make(map[nodeRFKey]*NodeRFRecord),
		channelSnapshots:          make(map[channelRFKey]*ChannelRFRecord),
		gatewaysSeen:              make(map[string]time.Time),
		nodeFreshnessThreshold:    DefaultNodeRFFreshness,
		channelFreshnessThreshold: DefaultChannelRFFreshness,
	}
}

// SetFreshnessThresholds configures node and channel freshness expiry durations.
func (t *RFTracker) SetFreshnessThresholds(nodeThresh, chThresh time.Duration) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if nodeThresh > 0 {
		t.nodeFreshnessThreshold = nodeThresh
	}
	if chThresh > 0 {
		t.channelFreshnessThreshold = chThresh
	}
}

// UpdateNodeRF ingests an RF sample for a node.
// Returns true if accepted, false if ignored as duplicate/out-of-order or invalid bounds.
func (t *RFTracker) UpdateNodeRF(
	gatewayID string,
	nodeID int,
	rssiDbm int,
	snrDb float64,
	channelIdx *int,
	source string,
	validation string,
	gatewayEpoch string,
	sampleSeq uint64,
	sampleMonotonicUS uint64,
	ageMs uint32,
) bool {
	if gatewayID == "" || gatewayEpoch == "" || nodeID < 1 || nodeID > 254 {
		return false
	}
	if channelIdx != nil && (*channelIdx < 0 || *channelIdx > 10) {
		return false
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	// Enforce gateway limit if new gateway
	if _, ok := t.gatewaysSeen[gatewayID]; !ok {
		if len(t.gatewaysSeen) >= MaxGatewaysTracked {
			return false
		}
		t.gatewaysSeen[gatewayID] = time.Now().UTC()
	}

	key := nodeRFKey{gatewayID: gatewayID, nodeID: nodeID}
	existing, exists := t.nodeSnapshots[key]
	if exists {
		if existing.GatewayEpoch == gatewayEpoch {
			// In the same boot epoch, sequence MUST be strictly monotonic.
			// Duplicate QoS1, WAL replays, and out-of-order samples are ignored.
			if sampleSeq <= existing.SampleSeq {
				return false
			}
		}
		// If gatewayEpoch changed, gateway rebooted -> accept new epoch
	}

	now := time.Now().UTC()
	measuredAt := now.Add(-time.Duration(ageMs) * time.Millisecond)

	var chCopy *int
	if channelIdx != nil {
		c := *channelIdx
		chCopy = &c
	}

	t.nodeSnapshots[key] = &NodeRFRecord{
		GatewayID:         gatewayID,
		NodeID:            nodeID,
		RssiDbm:           rssiDbm,
		SnrDb:             snrDb,
		ChannelIdx:        chCopy,
		Source:            source,
		Validation:        validation,
		GatewayEpoch:      gatewayEpoch,
		SampleSeq:         sampleSeq,
		SampleMonotonicUS: sampleMonotonicUS,
		AgeMs:             ageMs,
		ReceivedAt:        now,
		MeasuredAt:        measuredAt,
	}

	return true
}

// UpdateChannelRF ingests a channel energy sample for a gateway channel.
// Returns true if accepted, false if ignored as duplicate/out-of-order or invalid bounds.
func (t *RFTracker) UpdateChannelRF(
	gatewayID string,
	channelIdx int,
	channelRssiDbm int,
	sampleContext string,
	gatewayEpoch string,
	sampleSeq uint64,
	sampleMonotonicUS uint64,
	ageMs uint32,
) bool {
	if gatewayID == "" || gatewayEpoch == "" || channelIdx < 0 || channelIdx > 10 {
		return false
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	if _, ok := t.gatewaysSeen[gatewayID]; !ok {
		if len(t.gatewaysSeen) >= MaxGatewaysTracked {
			return false
		}
		t.gatewaysSeen[gatewayID] = time.Now().UTC()
	}

	key := channelRFKey{gatewayID: gatewayID, channelIdx: channelIdx}
	existing, exists := t.channelSnapshots[key]
	if exists {
		if existing.GatewayEpoch == gatewayEpoch {
			if sampleSeq <= existing.SampleSeq {
				return false
			}
		}
	}

	now := time.Now().UTC()
	measuredAt := now.Add(-time.Duration(ageMs) * time.Millisecond)

	t.channelSnapshots[key] = &ChannelRFRecord{
		GatewayID:         gatewayID,
		ChannelIdx:        channelIdx,
		ChannelRssiDbm:    channelRssiDbm,
		SampleContext:     sampleContext,
		GatewayEpoch:      gatewayEpoch,
		SampleSeq:         sampleSeq,
		SampleMonotonicUS: sampleMonotonicUS,
		AgeMs:             ageMs,
		ReceivedAt:        now,
		MeasuredAt:        measuredAt,
	}

	return true
}

// GetNodeRFView returns the latest RF view for a node under a specific gateway.
// Returns nil if no sample exists.
func (t *RFTracker) GetNodeRFView(gatewayID string, nodeID int) *NodeRFView {
	t.mu.RLock()
	defer t.mu.RUnlock()

	rec, ok := t.nodeSnapshots[nodeRFKey{gatewayID: gatewayID, nodeID: nodeID}]
	if !ok {
		return nil
	}

	now := time.Now().UTC()
	age := now.Sub(rec.MeasuredAt)
	if age < 0 {
		age = 0
	}
	ageSec := int(age.Seconds())
	stale := age > t.nodeFreshnessThreshold

	var chCopy *int
	if rec.ChannelIdx != nil {
		c := *rec.ChannelIdx
		chCopy = &c
	}

	return &NodeRFView{
		RssiDbm:      rec.RssiDbm,
		SnrDb:        rec.SnrDb,
		ChannelIdx:   chCopy,
		Source:       rec.Source,
		Validation:   rec.Validation,
		MeasuredAt:   rec.MeasuredAt,
		LastRfAt:     rec.MeasuredAt.Format(time.RFC3339),
		RfAgeSeconds: ageSec,
		RfStale:      stale,
	}
}

// GetLatestNodeRFView returns the latest RF view for a node across any gateway.
// If multiple gateways observed this node, the most recently measured sample is returned.
func (t *RFTracker) GetLatestNodeRFView(nodeID int) *NodeRFView {
	t.mu.RLock()
	defer t.mu.RUnlock()

	var latest *NodeRFRecord
	for key, rec := range t.nodeSnapshots {
		if key.nodeID == nodeID {
			if latest == nil || rec.MeasuredAt.After(latest.MeasuredAt) {
				latest = rec
			}
		}
	}

	if latest == nil {
		return nil
	}

	now := time.Now().UTC()
	age := now.Sub(latest.MeasuredAt)
	if age < 0 {
		age = 0
	}
	ageSec := int(age.Seconds())
	stale := age > t.nodeFreshnessThreshold

	var chCopy *int
	if latest.ChannelIdx != nil {
		c := *latest.ChannelIdx
		chCopy = &c
	}

	return &NodeRFView{
		RssiDbm:      latest.RssiDbm,
		SnrDb:        latest.SnrDb,
		ChannelIdx:   chCopy,
		Source:       latest.Source,
		Validation:   latest.Validation,
		MeasuredAt:   latest.MeasuredAt,
		LastRfAt:     latest.MeasuredAt.Format(time.RFC3339),
		RfAgeSeconds: ageSec,
		RfStale:      stale,
	}
}

// GetChannelRFView returns the latest channel RF view for a gateway.
// If channelIdx < 0, it selects the most recently updated channel for that gateway.
func (t *RFTracker) GetChannelRFView(gatewayID string, channelIdx int) *ChannelRFView {
	t.mu.RLock()
	defer t.mu.RUnlock()

	var rec *ChannelRFRecord
	if channelIdx >= 0 {
		rec = t.channelSnapshots[channelRFKey{gatewayID: gatewayID, channelIdx: channelIdx}]
	} else {
		for key, r := range t.channelSnapshots {
			if key.gatewayID == gatewayID {
				if rec == nil || r.MeasuredAt.After(rec.MeasuredAt) {
					rec = r
				}
			}
		}
	}

	if rec == nil {
		return nil
	}

	now := time.Now().UTC()
	age := now.Sub(rec.MeasuredAt)
	if age < 0 {
		age = 0
	}
	ageSec := int(age.Seconds())
	stale := age > t.channelFreshnessThreshold

	return &ChannelRFView{
		ChannelIdx:          rec.ChannelIdx,
		ChannelRssiDbm:      rec.ChannelRssiDbm,
		SampleContext:       rec.SampleContext,
		MeasuredAt:          rec.MeasuredAt,
		ChannelRfAt:         rec.MeasuredAt.Format(time.RFC3339),
		ChannelRfAgeSeconds: ageSec,
		ChannelRfStale:      stale,
	}
}

// RemoveNode purges all RF records for the specified nodeID.
func (t *RFTracker) RemoveNode(nodeID int) {
	t.mu.Lock()
	defer t.mu.Unlock()
	for key := range t.nodeSnapshots {
		if key.nodeID == nodeID {
			delete(t.nodeSnapshots, key)
		}
	}
}

// RemoveGateway purges all RF records associated with the specified gatewayID.
func (t *RFTracker) RemoveGateway(gatewayID string) {
	t.mu.Lock()
	defer t.mu.Unlock()
	for key := range t.nodeSnapshots {
		if key.gatewayID == gatewayID {
			delete(t.nodeSnapshots, key)
		}
	}
	for key := range t.channelSnapshots {
		if key.gatewayID == gatewayID {
			delete(t.channelSnapshots, key)
		}
	}
	delete(t.gatewaysSeen, gatewayID)
}

// Clear resets all stored RF state.
func (t *RFTracker) Clear() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.nodeSnapshots = make(map[nodeRFKey]*NodeRFRecord)
	t.channelSnapshots = make(map[channelRFKey]*ChannelRFRecord)
	t.gatewaysSeen = make(map[string]time.Time)
}
