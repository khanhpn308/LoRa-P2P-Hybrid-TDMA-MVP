package security_test

import (
	"bytes"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security"
)

func TestDeriveKJReq_Deterministic(t *testing.T) {
	networkID := uint32(0x01020304)
	deviceMAC := [6]byte{0x11, 0x22, 0x33, 0x44, 0x55, 0x66}
	deviceGen := uint16(1)
	var kJoin [security.KeySize]byte
	for i := range kJoin {
		kJoin[i] = byte(i + 1)
	}

	key1, err1 := security.DeriveKJReq(networkID, deviceMAC, deviceGen, kJoin)
	if err1 != nil {
		t.Fatalf("unexpected error deriving key1: %v", err1)
	}

	key2, err2 := security.DeriveKJReq(networkID, deviceMAC, deviceGen, kJoin)
	if err2 != nil {
		t.Fatalf("unexpected error deriving key2: %v", err2)
	}

	if !bytes.Equal(key1[:], key2[:]) {
		t.Fatalf("expected deterministic keys, got %x vs %x", key1, key2)
	}

	// Verify that changing generation produces a completely different key
	key3, err3 := security.DeriveKJReq(networkID, deviceMAC, deviceGen+1, kJoin)
	if err3 != nil {
		t.Fatalf("unexpected error deriving key3: %v", err3)
	}
	if bytes.Equal(key1[:], key3[:]) {
		t.Fatal("expected distinct keys for different generations")
	}

	// Verify that changing networkID produces a completely different key
	key4, err4 := security.DeriveKJReq(networkID+1, deviceMAC, deviceGen, kJoin)
	if err4 != nil {
		t.Fatalf("unexpected error deriving key4: %v", err4)
	}
	if bytes.Equal(key1[:], key4[:]) {
		t.Fatal("expected distinct keys for different network IDs")
	}
}

func TestComputeHelloProof_InvalidPrefixLength(t *testing.T) {
	var kjReq [security.KeySize]byte
	networkID := uint32(1)

	tests := []struct {
		name   string
		prefix []byte
	}{
		{"nil slice", nil},
		{"empty slice", []byte{}},
		{"truncated 51 bytes", make([]byte, 51)},
		{"oversized 53 bytes", make([]byte, 53)},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := security.ComputeHelloProof(networkID, tc.prefix, kjReq)
			if err == nil {
				t.Fatalf("expected error for invalid prefix length %d, got nil", len(tc.prefix))
			}
		})
	}
}

func TestVerifyHelloProof_Table(t *testing.T) {
	networkID := uint32(0x10203040)
	deviceMAC := [6]byte{0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF}
	deviceGen := uint16(2)
	var kJoin [security.KeySize]byte
	for i := range kJoin {
		kJoin[i] = byte(0x80 | i)
	}

	framePrefix := make([]byte, security.PrefixFrameLen)
	framePrefix[0] = 0x45 // VER_TYPE
	copy(framePrefix[1:7], deviceMAC[:])
	framePrefix[7] = 0x01 // TARGET_GW_ID
	framePrefix[8] = 0x00 // JOIN_COUNTER BE
	framePrefix[9] = 0x00
	framePrefix[10] = 0x00
	framePrefix[11] = 0x05 // counter = 5
	// Nonce and public key filled with dummy pattern
	for i := 12; i < security.PrefixFrameLen; i++ {
		framePrefix[i] = byte(i)
	}

	kjReq, err := security.DeriveKJReq(networkID, deviceMAC, deviceGen, kJoin)
	if err != nil {
		t.Fatalf("DeriveKJReq failed: %v", err)
	}

	validProof, err := security.ComputeHelloProof(networkID, framePrefix, kjReq)
	if err != nil {
		t.Fatalf("ComputeHelloProof failed: %v", err)
	}

	tests := []struct {
		name        string
		netID       uint32
		mac         [6]byte
		gen         uint16
		prefix      []byte
		proof       [security.ProofSize]byte
		key         [security.KeySize]byte
		expectError bool
	}{
		{
			name:        "valid proof passes",
			netID:       networkID,
			mac:         deviceMAC,
			gen:         deviceGen,
			prefix:      framePrefix,
			proof:       validProof,
			key:         kJoin,
			expectError: false,
		},
		{
			name:   "corrupted proof (single bit flip) fails",
			netID:  networkID,
			mac:    deviceMAC,
			gen:    deviceGen,
			prefix: framePrefix,
			proof: func() [security.ProofSize]byte {
				p := validProof
				p[0] ^= 0x01
				return p
			}(),
			key:         kJoin,
			expectError: true,
		},
		{
			name:        "wrong network ID fails",
			netID:       networkID ^ 0xFFFFFFFF,
			mac:         deviceMAC,
			gen:         deviceGen,
			prefix:      framePrefix,
			proof:       validProof,
			key:         kJoin,
			expectError: true,
		},
		{
			name:        "wrong device MAC fails",
			netID:       networkID,
			mac:         [6]byte{0x00, 0x01, 0x02, 0x03, 0x04, 0x05},
			gen:         deviceGen,
			prefix:      framePrefix,
			proof:       validProof,
			key:         kJoin,
			expectError: true,
		},
		{
			name:        "wrong device generation fails",
			netID:       networkID,
			mac:         deviceMAC,
			gen:         deviceGen + 1,
			prefix:      framePrefix,
			proof:       validProof,
			key:         kJoin,
			expectError: true,
		},
		{
			name:        "wrong kJoin fails",
			netID:       networkID,
			mac:         deviceMAC,
			gen:         deviceGen,
			prefix:      framePrefix,
			proof:       validProof,
			key:         [security.KeySize]byte{0xDE, 0xAD, 0xBE, 0xEF},
			expectError: true,
		},
		{
			name:  "tampered frame prefix byte fails",
			netID: networkID,
			mac:   deviceMAC,
			gen:   deviceGen,
			prefix: func() []byte {
				p := make([]byte, len(framePrefix))
				copy(p, framePrefix)
				p[15] ^= 0x02 // flip nonce bit
				return p
			}(),
			proof:       validProof,
			key:         kJoin,
			expectError: true,
		},
		{
			name:        "invalid prefix length returns error",
			netID:       networkID,
			mac:         deviceMAC,
			gen:         deviceGen,
			prefix:      framePrefix[:50],
			proof:       validProof,
			key:         kJoin,
			expectError: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := security.VerifyHelloProof(tc.netID, tc.mac, tc.gen, tc.prefix, tc.proof, tc.key)
			if tc.expectError && err == nil {
				t.Fatal("expected error, got nil")
			}
			if !tc.expectError && err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}
