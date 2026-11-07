package domain

import (
	"encoding/binary"
	"errors"
	"fmt"
	"math"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security"
)

const (
	// UpJoinHelloLength is the exact length in bytes of the UP_JOIN_HELLO frame.
	UpJoinHelloLength = 68

	// VerTypeUpJoinHello is the fixed byte code for UP_JOIN_HELLO (0x45).
	VerTypeUpJoinHello = 0x45

	// StatusHelloAuthenticatedPendingGrant is the exclusive success status at the Hello stage.
	StatusHelloAuthenticatedPendingGrant = "HELLO_AUTHENTICATED_PENDING_GRANT"

	// MinGatewayID is the minimum valid unicast gateway ID (0x01).
	MinGatewayID = 0x01
	// MaxGatewayID is the maximum valid unicast gateway ID (0xFE). 0x00 and 0xFF are reserved.
	MaxGatewayID = 0xFE
)

var (
	// ErrInvalidFrameLength indicates the raw frame is not exactly 68 bytes.
	ErrInvalidFrameLength = errors.New("frame length must be exactly 68 bytes")
	// ErrInvalidVerType indicates the VER_TYPE byte is not 0x45.
	ErrInvalidVerType = errors.New("invalid frame version/type; expected 0x45")
	// ErrInvalidGatewayID indicates TARGET_GW_ID is 0x00 or 0xFF.
	// ErrInvalidJoinCounter indicates JOIN_COUNTER is 0 or 0xFFFFFFFF.
	ErrInvalidJoinCounter = errors.New("join counter cannot be 0 or 0xFFFFFFFF")
	// ErrZeroDeviceMAC indicates DEVICE_MAC is all zeroes.
	ErrZeroDeviceMAC = errors.New("device MAC cannot be all zeroes")
	// ErrZeroX25519Pub indicates NODE_X25519_PUB is all zeroes (RFC 7748 §6.1).
	ErrZeroX25519Pub = errors.New("node X25519 public key cannot be all zeroes")
)

// UpJoinHelloFrame represents the parsed 68-byte UP_JOIN_HELLO frame.
//
// Layout:
//
//	VER_TYPE=0x45:1 | DEVICE_MAC:6 | TARGET_GW_ID:1 | JOIN_COUNTER:uint32BE:4 |
//	NODE_NONCE:8 | NODE_X25519_PUB:32 | JOIN_PROOF:16
type UpJoinHelloFrame struct {
	VerType       uint8
	DeviceMAC     [6]byte
	TargetGWID    uint8
	JoinCounter   uint32
	NodeNonce     [8]byte
	NodeX25519Pub [32]byte
	JoinProof     [16]byte
	RawPrefix52   [52]byte
}

// JoinHelloVerificationResult is the outcome of a successfully verified Hello frame.
// Adheres to DEC-SEC-01: Backend is zero-knowledge regarding data session keys Z.
// No session is created, no TDMA schedule or data TX rights granted at this stage.
type JoinHelloVerificationResult struct {
	Status           string
	DeviceMAC        [6]byte
	TargetGWID       uint8
	JoinCounter      uint32
	NodeNonce        [8]byte
	NodeX25519Pub    [32]byte
	NetworkID        uint32
	DeviceGeneration uint16
}

// ParseUpJoinHello parses and validates the wire framing of a raw 68-byte buffer.
// It fails closed on malformed input, invalid types, or out-of-range fields.
func ParseUpJoinHello(data []byte) (*UpJoinHelloFrame, error) {
	if len(data) != UpJoinHelloLength {
		return nil, fmt.Errorf("%w: got %d", ErrInvalidFrameLength, len(data))
	}

	if data[0] != VerTypeUpJoinHello {
		return nil, fmt.Errorf("%w: got 0x%02X", ErrInvalidVerType, data[0])
	}

	var frame UpJoinHelloFrame
	frame.VerType = data[0]
	copy(frame.DeviceMAC[:], data[1:7])
	frame.TargetGWID = data[7]
	frame.JoinCounter = binary.BigEndian.Uint32(data[8:12])
	copy(frame.NodeNonce[:], data[12:20])
	copy(frame.NodeX25519Pub[:], data[20:52])
	copy(frame.JoinProof[:], data[52:68])
	copy(frame.RawPrefix52[:], data[0:52])

	// Validate target gateway ID: 0x00 and 0xFF reserved
	if frame.TargetGWID < MinGatewayID || frame.TargetGWID > MaxGatewayID {
		return nil, fmt.Errorf("%w: got 0x%02X", ErrInvalidGatewayID, frame.TargetGWID)
	}

	// Validate monotonic JoinCounter: reject 0 and 0xFFFFFFFF
	if frame.JoinCounter == 0 || frame.JoinCounter == math.MaxUint32 {
		return nil, fmt.Errorf("%w: got %d", ErrInvalidJoinCounter, frame.JoinCounter)
	}

	// Validate DEVICE_MAC: reject all zeroes
	if isAllZero(frame.DeviceMAC[:]) {
		return nil, ErrZeroDeviceMAC
	}

	// Validate Node X25519 public key: reject all zeroes per RFC 7748 §6.1 / DEC-SEC-07
	if isAllZero(frame.NodeX25519Pub[:]) {
		return nil, ErrZeroX25519Pub
	}

	return &frame, nil
}

// VerifyUpJoinHello parses the 68-byte frame and cryptographically authenticates it
// using K_JOIN, networkID, and deviceGeneration.
// Constant-time HMAC comparison is strictly enforced via security.VerifyHelloProof.
func VerifyUpJoinHello(rawFrame []byte, networkID uint32, deviceGen uint16, kJoin [security.KeySize]byte) (*JoinHelloVerificationResult, error) {
	frame, err := ParseUpJoinHello(rawFrame)
	if err != nil {
		return nil, err
	}

	if err := security.VerifyHelloProof(networkID, frame.DeviceMAC, deviceGen, frame.RawPrefix52[:], frame.JoinProof, kJoin); err != nil {
		return nil, err
	}

	return &JoinHelloVerificationResult{
		Status:           StatusHelloAuthenticatedPendingGrant,
		DeviceMAC:        frame.DeviceMAC,
		TargetGWID:       frame.TargetGWID,
		JoinCounter:      frame.JoinCounter,
		NodeNonce:        frame.NodeNonce,
		NodeX25519Pub:    frame.NodeX25519Pub,
		NetworkID:        networkID,
		DeviceGeneration: deviceGen,
	}, nil
}

func isAllZero(b []byte) bool {
	var acc byte
	for _, x := range b {
		acc |= x
	}
	return acc == 0
}
