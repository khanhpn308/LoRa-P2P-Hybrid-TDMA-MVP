package domain_test

import (
	"encoding/binary"
	"errors"
	"math"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security"
)

func buildValidRawHello(netID uint32, mac [6]byte, gwID uint8, counter uint32, gen uint16, kJoin [security.KeySize]byte) []byte {
	raw := make([]byte, domain.UpJoinHelloLength)
	raw[0] = domain.VerTypeUpJoinHello
	copy(raw[1:7], mac[:])
	raw[7] = gwID
	binary.BigEndian.PutUint32(raw[8:12], counter)

	// Fill nonce and pubkey with non-zero test patterns
	for i := 12; i < 20; i++ {
		raw[i] = byte(i + 1)
	}
	for i := 20; i < 52; i++ {
		raw[i] = byte(i + 2)
	}

	kjReq, err := security.DeriveKJReq(netID, mac, gen, kJoin)
	if err != nil {
		panic(err)
	}

	proof, err := security.ComputeHelloProof(netID, raw[0:52], kjReq)
	if err != nil {
		panic(err)
	}
	copy(raw[52:68], proof[:])
	return raw
}

func TestParseUpJoinHello_Valid(t *testing.T) {
	mac := [6]byte{0x00, 0x11, 0x22, 0x33, 0x44, 0x55}
	raw := buildValidRawHello(1, mac, 0x05, 100, 1, [security.KeySize]byte{1})

	frame, err := domain.ParseUpJoinHello(raw)
	if err != nil {
		t.Fatalf("expected valid parse, got: %v", err)
	}

	if frame.VerType != domain.VerTypeUpJoinHello {
		t.Fatalf("expected ver_type 0x45, got 0x%02X", frame.VerType)
	}
	if frame.DeviceMAC != mac {
		t.Fatalf("expected MAC %x, got %x", mac, frame.DeviceMAC)
	}
	if frame.TargetGWID != 0x05 {
		t.Fatalf("expected GW ID 5, got %d", frame.TargetGWID)
	}
	if frame.JoinCounter != 100 {
		t.Fatalf("expected counter 100, got %d", frame.JoinCounter)
	}
}

func TestParseUpJoinHello_FramingBoundaries(t *testing.T) {
	mac := [6]byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06}
	base := buildValidRawHello(1, mac, 0x01, 1, 1, [security.KeySize]byte{1})

	tests := []struct {
		name        string
		modifier    func([]byte) []byte
		expectedErr error
	}{
		{
			name: "length too short (67B)",
			modifier: func(b []byte) []byte {
				return b[:67]
			},
			expectedErr: domain.ErrInvalidFrameLength,
		},
		{
			name: "length too long (69B)",
			modifier: func(b []byte) []byte {
				return append(b, 0x00)
			},
			expectedErr: domain.ErrInvalidFrameLength,
		},
		{
			name: "empty slice",
			modifier: func(b []byte) []byte {
				return []byte{}
			},
			expectedErr: domain.ErrInvalidFrameLength,
		},
		{
			name: "wrong ver_type (0x41 UP_EVENT)",
			modifier: func(b []byte) []byte {
				cpy := append([]byte(nil), b...)
				cpy[0] = 0x41
				return cpy
			},
			expectedErr: domain.ErrInvalidVerType,
		},
		{
			name: "wrong ver_type (0x07 V1 Join)",
			modifier: func(b []byte) []byte {
				cpy := append([]byte(nil), b...)
				cpy[0] = 0x07
				return cpy
			},
			expectedErr: domain.ErrInvalidVerType,
		},
		{
			name: "target gateway 0x00 reserved",
			modifier: func(b []byte) []byte {
				cpy := append([]byte(nil), b...)
				cpy[7] = 0x00
				return cpy
			},
			expectedErr: domain.ErrInvalidGatewayID,
		},
		{
			name: "target gateway 0xFF reserved",
			modifier: func(b []byte) []byte {
				cpy := append([]byte(nil), b...)
				cpy[7] = 0xFF
				return cpy
			},
			expectedErr: domain.ErrInvalidGatewayID,
		},
		{
			name: "join counter 0 forbidden",
			modifier: func(b []byte) []byte {
				cpy := append([]byte(nil), b...)
				binary.BigEndian.PutUint32(cpy[8:12], 0)
				return cpy
			},
			expectedErr: domain.ErrInvalidJoinCounter,
		},
		{
			name: "join counter 0xFFFFFFFF forbidden",
			modifier: func(b []byte) []byte {
				cpy := append([]byte(nil), b...)
				binary.BigEndian.PutUint32(cpy[8:12], math.MaxUint32)
				return cpy
			},
			expectedErr: domain.ErrInvalidJoinCounter,
		},
		{
			name: "all-zero device MAC rejected",
			modifier: func(b []byte) []byte {
				cpy := append([]byte(nil), b...)
				copy(cpy[1:7], []byte{0, 0, 0, 0, 0, 0})
				return cpy
			},
			expectedErr: domain.ErrZeroDeviceMAC,
		},
		{
			name: "all-zero node X25519 pubkey rejected (RFC 7748 §6.1)",
			modifier: func(b []byte) []byte {
				cpy := append([]byte(nil), b...)
				copy(cpy[20:52], make([]byte, 32))
				return cpy
			},
			expectedErr: domain.ErrZeroX25519Pub,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			input := tc.modifier(base)
			_, err := domain.ParseUpJoinHello(input)
			if err == nil {
				t.Fatalf("expected error %v, got nil", tc.expectedErr)
			}
			if !errors.Is(err, tc.expectedErr) {
				t.Fatalf("expected error wrapping %v, got %v", tc.expectedErr, err)
			}
		})
	}
}

func TestParseUpJoinHello_ValidBoundaries(t *testing.T) {
	mac := [6]byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06}

	// Min gateway ID 0x01
	rawMinGW := buildValidRawHello(1, mac, domain.MinGatewayID, 1, 1, [security.KeySize]byte{1})
	if _, err := domain.ParseUpJoinHello(rawMinGW); err != nil {
		t.Fatalf("MinGatewayID (0x01) should be valid, got: %v", err)
	}

	// Max gateway ID 0xFE
	rawMaxGW := buildValidRawHello(1, mac, domain.MaxGatewayID, 1, 1, [security.KeySize]byte{1})
	if _, err := domain.ParseUpJoinHello(rawMaxGW); err != nil {
		t.Fatalf("MaxGatewayID (0xFE) should be valid, got: %v", err)
	}

	// Min counter 1
	rawMinCounter := buildValidRawHello(1, mac, 0x01, 1, 1, [security.KeySize]byte{1})
	if _, err := domain.ParseUpJoinHello(rawMinCounter); err != nil {
		t.Fatalf("counter 1 should be valid, got: %v", err)
	}

	// Max counter math.MaxUint32 - 1
	rawMaxCounter := buildValidRawHello(1, mac, 0x01, math.MaxUint32-1, 1, [security.KeySize]byte{1})
	if _, err := domain.ParseUpJoinHello(rawMaxCounter); err != nil {
		t.Fatalf("counter MaxUint32-1 should be valid, got: %v", err)
	}
}

func TestVerifyUpJoinHello_SuccessAndFailure(t *testing.T) {
	netID := uint32(42)
	mac := [6]byte{0xDE, 0xAD, 0xBE, 0xEF, 0x01, 0x02}
	gen := uint16(1)
	var kJoin [security.KeySize]byte
	for i := range kJoin {
		kJoin[i] = byte(0x55 ^ i)
	}

	validRaw := buildValidRawHello(netID, mac, 0x10, 42, gen, kJoin)

	// 1. Success case
	res, err := domain.VerifyUpJoinHello(validRaw, netID, gen, kJoin)
	if err != nil {
		t.Fatalf("expected successful verification, got: %v", err)
	}

	if res.Status != domain.StatusHelloAuthenticatedPendingGrant {
		t.Fatalf("expected status %s, got %s", domain.StatusHelloAuthenticatedPendingGrant, res.Status)
	}
	if res.DeviceMAC != mac || res.TargetGWID != 0x10 || res.JoinCounter != 42 {
		t.Fatalf("result fields mismatch: %+v", res)
	}
	if res.NetworkID != netID || res.DeviceGeneration != gen {
		t.Fatalf("network/generation mismatch: %+v", res)
	}

	// 2. Proof mismatch case (corrupted proof)
	corruptedRaw := append([]byte(nil), validRaw...)
	corruptedRaw[60] ^= 0xFF
	_, err = domain.VerifyUpJoinHello(corruptedRaw, netID, gen, kJoin)
	if err == nil {
		t.Fatal("expected proof mismatch error, got nil")
	}
	if !errors.Is(err, security.ErrProofMismatch) {
		t.Fatalf("expected ErrProofMismatch, got: %v", err)
	}

	// 3. Framing error fails before crypto check
	truncatedRaw := validRaw[:60]
	_, err = domain.VerifyUpJoinHello(truncatedRaw, netID, gen, kJoin)
	if err == nil {
		t.Fatal("expected framing error, got nil")
	}
	if !errors.Is(err, domain.ErrInvalidFrameLength) {
		t.Fatalf("expected ErrInvalidFrameLength, got: %v", err)
	}
}
