package mqtt

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

const (
	// DefaultMaxPayloadBytes is the default bounding limit for MQTT Join relay envelope payloads.
	DefaultMaxPayloadBytes = 2048
)

var (
	// ErrPayloadTooLarge indicates the message payload exceeds the bounded size limit.
	ErrPayloadTooLarge = errors.New("relay envelope payload exceeds maximum allowed size")
	// ErrIdentityMismatch indicates the authenticated broker principal does not match the topic or payload gateway ID.
	ErrIdentityMismatch = errors.New("authenticated gateway identity does not match topic or payload")
	// ErrTargetGWMismatch indicates the target gateway ID in the frame does not match receiving gateway assignment.
	ErrTargetGWMismatch = errors.New("target gateway ID does not match receiving gateway assignment")
	// ErrAuthenticationFailed indicates cryptographic authentication or device lookup failed (sanitized).
	ErrAuthenticationFailed = errors.New("join hello authentication failed")
	// ErrReplayDetected indicates a replay attack was detected with a conflicting payload hash.
	ErrReplayDetected = errors.New("conflicting replay detected for join counter")
	// ErrStaleJoinCounter indicates the join counter is stale or has rolled back.
	ErrStaleJoinCounter = errors.New("join counter is stale or has rolled back")
	// ErrZeroDataGrantViolation indicates the outcome attempted to grant data transmission rights at the Hello phase.
	ErrZeroDataGrantViolation = errors.New("invalid transaction status: Hello stage must not grant data transmission rights")
)

// IngestRequest encapsulates an incoming MQTT relay message for ingestion.
type IngestRequest struct {
	Topic           string
	Payload         []byte
	BrokerGatewayID string // Authenticated identity from broker mTLS/TLS client principal
}

// IngestResponse represents the verified outcome of an authenticated and persisted Join Hello message.
type IngestResponse struct {
	TransactionID      int64
	Status             string
	IsIdempotentReplay bool
	JoinCounter        uint32
	DeviceMAC          [6]byte
	GatewayID          string
}

// JoinHelloIngestHandler handles the decoding, identity binding, cryptographic verification,
// and idempotent persistence of UP_JOIN_HELLO relay messages.
type JoinHelloIngestHandler struct {
	joinRepo        storage.JoinRepository
	gwDir           GatewayDirectory
	keyUnwrapper    KeyUnwrapper
	rateLimiter     RateLimiter
	maxPayloadBytes int
}

// HandlerConfig holds configuration parameters for JoinHelloIngestHandler.
type HandlerConfig struct {
	JoinRepo        storage.JoinRepository
	GatewayDir      GatewayDirectory
	KeyUnwrapper    KeyUnwrapper
	RateLimiter     RateLimiter
	MaxPayloadBytes int
}

// NewJoinHelloIngestHandler constructs a new JoinHelloIngestHandler with validated dependencies.
func NewJoinHelloIngestHandler(cfg HandlerConfig) (*JoinHelloIngestHandler, error) {
	if cfg.JoinRepo == nil {
		return nil, errors.New("JoinRepo dependency is required")
	}
	if cfg.GatewayDir == nil {
		return nil, errors.New("GatewayDir dependency is required")
	}
	if cfg.KeyUnwrapper == nil {
		cfg.KeyUnwrapper = NewPlainKeyUnwrapper()
	}
	if cfg.RateLimiter == nil {
		cfg.RateLimiter = &NoopRateLimiter{}
	}
	if cfg.MaxPayloadBytes <= 0 {
		cfg.MaxPayloadBytes = DefaultMaxPayloadBytes
	}

	return &JoinHelloIngestHandler{
		joinRepo:        cfg.JoinRepo,
		gwDir:           cfg.GatewayDir,
		keyUnwrapper:    cfg.KeyUnwrapper,
		rateLimiter:     cfg.RateLimiter,
		maxPayloadBytes: cfg.MaxPayloadBytes,
	}, nil
}

// Handle processes an incoming Join Hello relay envelope from MQTT.
// Adheres strictly to JH-01..JH-08 and Go Standard v2 rules:
// - Bounded payload sizes and timeouts
// - Broker authenticated principal binding
// - Zero knowledge: Gateway never handles keys
// - Constant-time cryptographic HMAC verification via HKDF
// - Database row-level locks and monotonic anti-replay idempotency
// - Sanitized error reporting preventing device enumeration or secret leakage
// - Zero data transmission rights granted at Hello stage
func (h *JoinHelloIngestHandler) Handle(ctx context.Context, req IngestRequest) (*IngestResponse, error) {
	// 1. Check payload boundary
	if len(req.Payload) > h.maxPayloadBytes {
		return nil, fmt.Errorf("%w: size=%d, max=%d", ErrPayloadTooLarge, len(req.Payload), h.maxPayloadBytes)
	}

	// 2. Validate topic format and extract gateway ID
	topicGWID, err := ParseJoinHelloTopic(req.Topic)
	if err != nil {
		return nil, err
	}

	// 3. JH-02: Identity Binding — Verify authenticated broker identity matches topic
	if req.BrokerGatewayID != "" && req.BrokerGatewayID != topicGWID {
		return nil, fmt.Errorf("%w: broker=%q, topic=%q", ErrIdentityMismatch, req.BrokerGatewayID, topicGWID)
	}

	// 4. Rate-limit check per gateway identity
	if !h.rateLimiter.Allow(ctx, "gw:"+topicGWID) {
		return nil, fmt.Errorf("%w: gateway=%q", ErrRateLimited, topicGWID)
	}

	// 5. Decode JSON using jsonboundary (rejects duplicate keys and unknown members)
	var envelope JoinHelloEnvelope
	if err := jsonboundary.DecodeObject(req.Payload, h.maxPayloadBytes, &envelope); err != nil {
		return nil, fmt.Errorf("decode envelope JSON: %w", err)
	}

	// 6. JH-02: Verify payload gateway_id matches topic
	if envelope.GatewayID != topicGWID {
		return nil, fmt.Errorf("%w: payload=%q, topic=%q", ErrIdentityMismatch, envelope.GatewayID, topicGWID)
	}

	// 7. Validate envelope schema rules (JH-01..JH-07)
	if err := envelope.Validate(); err != nil {
		return nil, err
	}

	// 8. Authorize gateway in registry and check active state & numeric ID
	gwInfo, err := h.gwDir.LookupGateway(ctx, topicGWID)
	if err != nil {
		return nil, fmt.Errorf("gateway authorization failed: %w", err)
	}
	if gwInfo.NumericID != uint8(envelope.TargetGWID) {
		return nil, fmt.Errorf("%w: assigned=%d, targeted=%d", ErrTargetGWMismatch, gwInfo.NumericID, envelope.TargetGWID)
	}

	// 9. Decode 68-byte raw frame
	rawFrame, err := envelope.DecodeRawFrameHex()
	if err != nil {
		return nil, err
	}

	// Validate wire invariants: VER_TYPE = 0x45, TARGET_GW_ID = rawFrame[7]
	if rawFrame[0] != domain.VerTypeUpJoinHello {
		return nil, fmt.Errorf("%w: byte0=0x%02X", domain.ErrInvalidVerType, rawFrame[0])
	}
	if rawFrame[7] != uint8(envelope.TargetGWID) {
		return nil, fmt.Errorf("%w: frame target_gw_id=%d, envelope=%d", ErrTargetGWMismatch, rawFrame[7], envelope.TargetGWID)
	}

	// Extract device MAC
	var deviceMAC [6]byte
	copy(deviceMAC[:], rawFrame[1:7])

	// Rate-limit check per device MAC
	macKey := fmt.Sprintf("mac:%02x%02x%02x%02x%02x%02x", deviceMAC[0], deviceMAC[1], deviceMAC[2], deviceMAC[3], deviceMAC[4], deviceMAC[5])
	if !h.rateLimiter.Allow(ctx, macKey) {
		return nil, fmt.Errorf("%w: mac=%s", ErrRateLimited, macKey)
	}

	// 10. Query active device registration from storage
	deviceRecord, err := h.joinRepo.GetActiveDevice(ctx, gwInfo.NetworkID, deviceMAC)
	if err != nil {
		// Anti-enumeration (SE-007): sanitize ErrDeviceNotFound / ErrDeviceNotActive
		return nil, ErrAuthenticationFailed
	}

	// 11. Unwrap K_JOIN secret
	kJoin, err := h.keyUnwrapper.UnwrapKJoin(ctx, gwInfo.NetworkID, deviceMAC, deviceRecord.ActiveGeneration, deviceRecord.KJoinWrapped)
	if err != nil {
		return nil, ErrAuthenticationFailed
	}
	// Secure zeroize K_JOIN after authentication
	defer func() {
		for i := range kJoin {
			kJoin[i] = 0
		}
	}()

	// 12. Authenticate frame with HKDF-SHA256 and constant-time HMAC proof
	authResult, err := domain.VerifyUpJoinHello(rawFrame, gwInfo.NetworkID, deviceRecord.ActiveGeneration, kJoin)
	if err != nil {
		return nil, ErrAuthenticationFailed
	}

	// 13. Compute raw frame SHA256 for idempotency matching
	rawHelloSHA256 := sha256.Sum256(rawFrame)

	// 14. Delegate to storage for row-level lock and anti-replay idempotency
	txInput := &storage.JoinHelloTxInput{
		NetworkID:      gwInfo.NetworkID,
		DeviceMAC:      deviceMAC,
		Generation:     deviceRecord.ActiveGeneration,
		TargetGWID:     authResult.TargetGWID,
		JoinCounter:    authResult.JoinCounter,
		RawHelloSHA256: rawHelloSHA256,
		NodeNonce:      authResult.NodeNonce,
		NodeX25519Pub:  authResult.NodeX25519Pub,
	}

	txResult, err := h.joinRepo.RecordJoinHello(ctx, txInput)
	if err != nil {
		if errors.Is(err, storage.ErrReplayDetected) {
			return nil, fmt.Errorf("%w: %w", ErrReplayDetected, err)
		}
		if errors.Is(err, storage.ErrStaleJoinCounter) {
			return nil, fmt.Errorf("%w: %w", ErrStaleJoinCounter, err)
		}
		return nil, fmt.Errorf("record join hello: %w", err)
	}

	// 15. JH-08 Invariant: Status must be HELLO_AUTHENTICATED_PENDING_GRANT
	if txResult.Status != domain.StatusHelloAuthenticatedPendingGrant {
		return nil, fmt.Errorf("%w: got %q", ErrZeroDataGrantViolation, txResult.Status)
	}

	return &IngestResponse{
		TransactionID:      txResult.TransactionID,
		Status:             txResult.Status,
		IsIdempotentReplay: txResult.IsIdempotentReplay,
		JoinCounter:        txResult.JoinCounter,
		DeviceMAC:          deviceMAC,
		GatewayID:          topicGWID,
	}, nil
}
