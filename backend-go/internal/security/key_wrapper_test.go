package security_test

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"encoding/hex"
	"encoding/json"
	"os"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security"
)

func testMasterKey() [32]byte {
	var k [32]byte
	for i := range k {
		k[i] = byte(i + 1)
	}
	return k
}

// TestAESGCMKeyWrapper_RoundTrip preserves the exact relocated baseline test logic.
func TestAESGCMKeyWrapper_RoundTrip(t *testing.T) {
	masterKey := testMasterKey()
	wrapper := security.NewAESGCMKeyWrapper(masterKey)

	rawKey := make([]byte, 32)
	for i := range rawKey {
		rawKey[i] = byte(i * 3)
	}

	wrapped, err := wrapper.Wrap(rawKey)
	if err != nil {
		t.Fatalf("Wrap failed: %v", err)
	}

	// 12-byte nonce + 32-byte ciphertext + 16-byte tag = 60 bytes
	if len(wrapped) != 60 {
		t.Fatalf("expected wrapped length 60, got %d", len(wrapped))
	}

	unwrapped, err := wrapper.Unwrap(wrapped)
	if err != nil {
		t.Fatalf("Unwrap failed: %v", err)
	}

	if !bytes.Equal(unwrapped, rawKey) {
		t.Fatalf("unwrapped bytes do not match original plaintext")
	}

	// Tampered ciphertext should fail auth tag verification
	wrapped[len(wrapped)-1] ^= 0xFF
	_, err = wrapper.Unwrap(wrapped)
	if err == nil {
		t.Fatalf("expected authentication failure on tampered wrapped key")
	}

	// Payload too short
	_, err = wrapper.Unwrap([]byte("short"))
	if err == nil {
		t.Fatalf("expected error on short payload in Unwrap")
	}
}

// TestAESGCMKeyWrapper_PlaintextSizes verifies round-trip behavior for 0, 1, 16, 32, and 64 byte plaintexts.
func TestAESGCMKeyWrapper_PlaintextSizes(t *testing.T) {
	masterKey := testMasterKey()
	wrapper := security.NewAESGCMKeyWrapper(masterKey)

	cases := []struct {
		name        string
		size        int
		expectedLen int
	}{
		{"empty_0b", 0, 28},
		{"single_1b", 1, 29},
		{"block_16b", 16, 44},
		{"kjoin_32b", 32, 60},
		{"double_64b", 64, 92},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			plaintext := make([]byte, tc.size)
			for i := range plaintext {
				plaintext[i] = byte(i*7 + 11)
			}

			envelope, err := wrapper.Wrap(plaintext)
			if err != nil {
				t.Fatalf("Wrap failed for size %d: %v", tc.size, err)
			}

			// Invariant: expected envelope length = plaintext length + 28 (12B nonce + 16B tag)
			if len(envelope) != tc.expectedLen {
				t.Fatalf("expected envelope length %d, got %d", tc.expectedLen, len(envelope))
			}

			decrypted, err := wrapper.Unwrap(envelope)
			if err != nil {
				t.Fatalf("Unwrap failed for size %d: %v", tc.size, err)
			}

			if !bytes.Equal(decrypted, plaintext) {
				t.Fatalf("decrypted bytes do not match original plaintext")
			}
		})
	}
}

// TestAESGCMKeyWrapper_ShortEnvelopes verifies that any envelope shorter than 28 bytes
// is rejected with the exact error message: "wrapped key payload too short".
func TestAESGCMKeyWrapper_ShortEnvelopes(t *testing.T) {
	masterKey := testMasterKey()
	wrapper := security.NewAESGCMKeyWrapper(masterKey)

	const expectedErrMsg = "wrapped key payload too short"

	for length := 0; length < 28; length++ {
		payload := make([]byte, length)
		for i := range payload {
			payload[i] = byte(i)
		}

		_, err := wrapper.Unwrap(payload)
		if err == nil {
			t.Fatalf("expected error for payload length %d, got nil", length)
		}
		if err.Error() != expectedErrMsg {
			t.Fatalf("length %d: expected error %q, got %q", length, expectedErrMsg, err.Error())
		}
	}
}

// TestAESGCMKeyWrapper_Tampering verifies that tampering with nonce, ciphertext, or auth tag fails authentication.
func TestAESGCMKeyWrapper_Tampering(t *testing.T) {
	masterKey := testMasterKey()
	wrapper := security.NewAESGCMKeyWrapper(masterKey)

	plaintext := make([]byte, 32)
	for i := range plaintext {
		plaintext[i] = byte(i + 42)
	}

	originalEnvelope, err := wrapper.Wrap(plaintext)
	if err != nil {
		t.Fatalf("Wrap failed: %v", err)
	}

	// 1. Nonce tampering (bytes 0..11)
	t.Run("nonce_tampering", func(t *testing.T) {
		for idx := 0; idx < 12; idx++ {
			tampered := append([]byte(nil), originalEnvelope...)
			tampered[idx] ^= 0x01
			_, err := wrapper.Unwrap(tampered)
			if err == nil {
				t.Fatalf("expected error on nonce byte %d tampering, got nil", idx)
			}
		}
	})

	// 2. Ciphertext tampering (bytes 12..43)
	t.Run("ciphertext_tampering", func(t *testing.T) {
		for idx := 12; idx < 44; idx++ {
			tampered := append([]byte(nil), originalEnvelope...)
			tampered[idx] ^= 0x01
			_, err := wrapper.Unwrap(tampered)
			if err == nil {
				t.Fatalf("expected error on ciphertext byte %d tampering, got nil", idx)
			}
		}
	})

	// 3. Tag tampering (bytes 44..59)
	t.Run("tag_tampering", func(t *testing.T) {
		for idx := 44; idx < len(originalEnvelope); idx++ {
			tampered := append([]byte(nil), originalEnvelope...)
			tampered[idx] ^= 0x01
			_, err := wrapper.Unwrap(tampered)
			if err == nil {
				t.Fatalf("expected error on tag byte %d tampering, got nil", idx)
			}
		}
	})

	// 4. Truncated authenticated envelopes (e.g. 59, 50, 44, 28 bytes)
	t.Run("truncated_authenticated_envelopes", func(t *testing.T) {
		truncatedLengths := []int{59, 50, 44, 32, 28}
		for _, tl := range truncatedLengths {
			truncated := originalEnvelope[:tl]
			_, err := wrapper.Unwrap(truncated)
			if err == nil {
				t.Fatalf("expected error on truncated envelope length %d, got nil", tl)
			}
		}
	})
}

// TestAESGCMKeyWrapper_WrongKey verifies that unwrapping with a mismatched master key fails authentication.
func TestAESGCMKeyWrapper_WrongKey(t *testing.T) {
	key1 := testMasterKey()
	var key2 [32]byte
	for i := range key2 {
		key2[i] = byte(i + 2)
	}

	wrapper1 := security.NewAESGCMKeyWrapper(key1)
	wrapper2 := security.NewAESGCMKeyWrapper(key2)

	plaintext := []byte("secret payload for key test")
	envelope, err := wrapper1.Wrap(plaintext)
	if err != nil {
		t.Fatalf("Wrap failed: %v", err)
	}

	_, err = wrapper2.Unwrap(envelope)
	if err == nil {
		t.Fatalf("expected unwrap with wrong key to fail authentication, got nil")
	}
}

// TestAESGCMKeyWrapper_IndependentLayoutVerification verifies the envelope layout independently
// using standard library crypto/aes and crypto/cipher primitives directly.
func TestAESGCMKeyWrapper_IndependentLayoutVerification(t *testing.T) {
	masterKey := testMasterKey()
	wrapper := security.NewAESGCMKeyWrapper(masterKey)

	plaintext := []byte("independent-layout-verification-32b")
	envelope, err := wrapper.Wrap(plaintext)
	if err != nil {
		t.Fatalf("Wrap failed: %v", err)
	}

	// Layout invariant: nonce (12 bytes) || ciphertext || tag (16 bytes)
	if len(envelope) != 12+len(plaintext)+16 {
		t.Fatalf("expected envelope length %d, got %d", 12+len(plaintext)+16, len(envelope))
	}

	nonce := envelope[:12]
	ciphertextAndTag := envelope[12:]

	block, err := aes.NewCipher(masterKey[:])
	if err != nil {
		t.Fatalf("aes.NewCipher failed: %v", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		t.Fatalf("cipher.NewGCM failed: %v", err)
	}

	decrypted, err := gcm.Open(nil, nonce, ciphertextAndTag, nil)
	if err != nil {
		t.Fatalf("stdlib gcm.Open failed on wrapper envelope: %v", err)
	}

	if !bytes.Equal(decrypted, plaintext) {
		t.Fatalf("stdlib gcm.Open output does not match plaintext")
	}
}

// TestAESGCMKeyWrapper_RepeatedWrapCSPRNG verifies that 1,000 repeated Wrap calls produce unique nonces.
// Note: Observed sample evidence, not a mathematical guarantee of nonce uniqueness.
func TestAESGCMKeyWrapper_RepeatedWrapCSPRNG(t *testing.T) {
	masterKey := testMasterKey()
	wrapper := security.NewAESGCMKeyWrapper(masterKey)

	seenNonces := make(map[[12]byte]struct{}, 1000)
	plaintext := []byte("sample-data-for-cspng-check")

	for i := 0; i < 1000; i++ {
		envelope, err := wrapper.Wrap(plaintext)
		if err != nil {
			t.Fatalf("Wrap failed on iteration %d: %v", i, err)
		}

		var nonce [12]byte
		copy(nonce[:], envelope[:12])

		if _, exists := seenNonces[nonce]; exists {
			t.Fatalf("duplicate nonce observed on iteration %d: %x", i, nonce)
		}
		seenNonces[nonce] = struct{}{}
	}

	if len(seenNonces) != 1000 {
		t.Fatalf("expected 1000 unique nonces, got %d", len(seenNonces))
	}
}

// TestAESGCMKeyWrapper_BaseCompatibility verifies that candidate Unwrap decrypts actual BASE
// ciphertext byte-for-byte using synthetic fixtures generated by BASE at cab72b040703277ca91e9f0fefee301141ef261f.
func TestAESGCMKeyWrapper_BaseCompatibility(t *testing.T) {
	// Provenance: BASE commit cab72b040703277ca91e9f0fefee301141ef261f
	// Synthetic master key: 0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20
	var masterKey [32]byte
	for i := range masterKey {
		masterKey[i] = byte(i + 1)
	}

	wrapper := security.NewAESGCMKeyWrapper(masterKey)

	fixtures := []struct {
		name         string
		plaintextHex string
		envelopeHex  string
		expectedLen  int
	}{
		{
			name:         "empty_0b",
			plaintextHex: "",
			envelopeHex:  "44556e22b61dd574db1b57db7201bc16e7d4982b906709fc94ace65f",
			expectedLen:  28,
		},
		{
			name:         "single_1b",
			plaintextHex: "42",
			envelopeHex:  "43db3547161768f141c49aa1bc75a4496f949ad152879889495578120b",
			expectedLen:  29,
		},
		{
			name:         "block_16b",
			plaintextHex: "30313233343536373839616263646566",
			envelopeHex:  "a7eccde0748340065fefd7b0199923109c9b40607d3c6ca11186339d4fdb58d9d7fb1e121abbe94452d0a4e2",
			expectedLen:  44,
		},
		{
			name:         "kjoin_32b",
			plaintextHex: "3031323334353637383961626364656630313233343536373839616263646566",
			envelopeHex:  "aaa85fcea54a003d82e6ae5c88f1d81a3671ec6b724b252697b15064c9c98216a9924e390fc88c672e65ed16acece344739ee620ed16e4e61b149c6e",
			expectedLen:  60,
		},
		{
			name:         "double_64b",
			plaintextHex: "30313233343536373839616263646566303132333435363738396162636465663031323334353637383961626364656630313233343536373839616263646566",
			envelopeHex:  "425a3ff73b5975eab5f0ce95aa65f8e5558795a24d66577a6bbac0039296694c7695fefc6fbde6b9bffdf26c8a3f3988b3c118887c39162b2e1dc48eb0c79487d0eb705aaf03b152ca4336c74decaf1cb182bbdc3424c2a5a68ed00d",
			expectedLen:  92,
		},
	}

	for _, tc := range fixtures {
		t.Run(tc.name, func(t *testing.T) {
			expectedPlaintext, err := hex.DecodeString(tc.plaintextHex)
			if err != nil {
				t.Fatalf("hex decode plaintext failed: %v", err)
			}

			envelope, err := hex.DecodeString(tc.envelopeHex)
			if err != nil {
				t.Fatalf("hex decode envelope failed: %v", err)
			}

			if len(envelope) != tc.expectedLen {
				t.Fatalf("envelope length mismatch: expected %d, got %d", tc.expectedLen, len(envelope))
			}

			decrypted, err := wrapper.Unwrap(envelope)
			if err != nil {
				t.Fatalf("Unwrap failed on BASE fixture: %v", err)
			}

			if !bytes.Equal(decrypted, expectedPlaintext) {
				t.Fatalf("decrypted output mismatch for fixture %s", tc.name)
			}
		})
	}
}

// TestAESGCMKeyWrapper_DumpCandidateWrap produces synthetic wrap envelopes to verify that
// the BASE implementation can decrypt candidate output in a cross-version verification harness.
func TestAESGCMKeyWrapper_DumpCandidateWrap(t *testing.T) {
	outPath := os.Getenv("DUMP_CANDIDATE_WRAP")
	if outPath == "" {
		return
	}

	masterKey := testMasterKey()
	wrapper := security.NewAESGCMKeyWrapper(masterKey)

	plaintexts := []struct {
		name string
		data []byte
	}{
		{"empty_0b", []byte{}},
		{"single_1b", []byte{0x42}},
		{"block_16b", []byte("candidate-16-bytes")[:16]},
		{"kjoin_32b", []byte("candidate-32-byte-kjoin-payload-")[:32]},
		{"double_64b", []byte("candidate-64-byte-payload-for-testing-envelope-compatibility-bytes")[:64]},
	}

	type Fixture struct {
		Name         string `json:"name"`
		PlaintextHex string `json:"plaintext_hex"`
		EnvelopeHex  string `json:"envelope_hex"`
		EnvelopeLen  int    `json:"envelope_len"`
	}

	type Output struct {
		MasterKeyHex string    `json:"master_key_hex"`
		Fixtures     []Fixture `json:"fixtures"`
	}

	var fixtures []Fixture
	for _, pt := range plaintexts {
		env, err := wrapper.Wrap(pt.data)
		if err != nil {
			t.Fatalf("Wrap failed: %v", err)
		}
		fixtures = append(fixtures, Fixture{
			Name:         pt.name,
			PlaintextHex: hex.EncodeToString(pt.data),
			EnvelopeHex:  hex.EncodeToString(env),
			EnvelopeLen:  len(env),
		})
	}

	data, err := json.MarshalIndent(Output{
		MasterKeyHex: hex.EncodeToString(masterKey[:]),
		Fixtures:     fixtures,
	}, "", "  ")
	if err != nil {
		t.Fatalf("Marshal failed: %v", err)
	}

	if err := os.WriteFile(outPath, data, 0644); err != nil {
		t.Fatalf("WriteFile failed: %v", err)
	}
}
