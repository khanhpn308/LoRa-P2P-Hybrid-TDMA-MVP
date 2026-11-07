package mqtt

import (
	"context"
	"errors"
	"fmt"
	"sync"
)

var (
	// ErrGatewayNotFound indicates the gateway is not registered in the system.
	ErrGatewayNotFound = errors.New("gateway not found")
	// ErrGatewayInactive indicates the gateway is suspended or deactivated.
	ErrGatewayInactive = errors.New("gateway is inactive")
)

// GatewayInfo holds authorized gateway metadata and identity bindings.
type GatewayInfo struct {
	GatewayID string // String identifier, e.g. "gw-north-01"
	NumericID uint8  // Unicast numeric ID 0x01..0xFE (1..254)
	NetworkID uint32 // Authoritative Network ID
	IsActive  bool   // Whether the gateway is administratively active
}

// GatewayDirectory resolves gateway identities and authorizes incoming relay topics.
type GatewayDirectory interface {
	LookupGateway(ctx context.Context, gatewayID string) (*GatewayInfo, error)
}

// StaticGatewayDirectory provides an in-memory, thread-safe implementation of GatewayDirectory.
type StaticGatewayDirectory struct {
	mu       sync.RWMutex
	gateways map[string]GatewayInfo
}

// NewStaticGatewayDirectory creates a new StaticGatewayDirectory with initial entries.
func NewStaticGatewayDirectory(entries ...GatewayInfo) *StaticGatewayDirectory {
	dir := &StaticGatewayDirectory{
		gateways: make(map[string]GatewayInfo, len(entries)),
	}
	for _, gw := range entries {
		dir.gateways[gw.GatewayID] = gw
	}
	return dir
}

// LookupGateway retrieves the gateway metadata by string ID.
func (d *StaticGatewayDirectory) LookupGateway(ctx context.Context, gatewayID string) (*GatewayInfo, error) {
	d.mu.RLock()
	defer d.mu.RUnlock()

	gw, ok := d.gateways[gatewayID]
	if !ok {
		return nil, fmt.Errorf("%w: %q", ErrGatewayNotFound, gatewayID)
	}
	if !gw.IsActive {
		return nil, fmt.Errorf("%w: %q", ErrGatewayInactive, gatewayID)
	}

	res := gw
	return &res, nil
}

// RegisterGateway adds or updates an authorized gateway in the directory.
func (d *StaticGatewayDirectory) RegisterGateway(gw GatewayInfo) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.gateways[gw.GatewayID] = gw
}
