package security

import (
	"crypto/hkdf"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/binary"
	"errors"
	"fmt"
)

var (
	// ErrProofMismatch is returned when the calculated Join proof does not match the frame proof.
	ErrProofMismatch = errors.New("join proof verification failed")
	// ErrInvalidInput is returned when cryptographic parameters are malformed.
	ErrInvalidInput = errors.New("invalid cryptographic input parameter")
)

const (
	// JoinRootSaltPrefix is the domain separation string for the join root salt.
	JoinRootSaltPrefix = "LP2P/V2/JOIN-ROOT"
	// JoinReqInfo is the HKDF expand info string for the join request key.
	JoinReqInfo = "LP2P/V2/JOIN-REQ"
	// JoinHelloTranscriptPrefix is the domain separation string for the Hello transcript.
	JoinHelloTranscriptPrefix = "LP2P/V2/M-HELLO"
	// KeySize is the expected key size in bytes for K_JOIN and K_JREQ (32 bytes).
	KeySize = 32
	// ProofSize is the size of the truncated HMAC proof (16 bytes).
	ProofSize = 16
	// PrefixFrameLen is the length of RF_FRAME[0..51] included in M_HELLO.
	PrefixFrameLen = 52
)

// DeriveKJReq derives K_JREQ from pre-shared K_JOIN and session parameters using HKDF-SHA256.
//
// Formula:
//
//	SALT = ASCII("LP2P/V2/JOIN-ROOT") || NETWORK_ID_BE4 || DEVICE_MAC6 || DEVICE_GENERATION_BE2
//	PRK = HKDF-Extract-SHA256(salt=SALT, IKM=K_JOIN)
//	K_JREQ = HKDF-Expand-SHA256(PRK, info=ASCII("LP2P/V2/JOIN-REQ"), L=32)
func DeriveKJReq(networkID uint32, deviceMAC [6]byte, deviceGen uint16, kJoin [KeySize]byte) ([KeySize]byte, error) {
	// Build SALT: 17B prefix + 4B network + 6B MAC + 2B generation = 29B
	salt := make([]byte, 0, len(JoinRootSaltPrefix)+4+6+2)
	salt = append(salt, []byte(JoinRootSaltPrefix)...)
	var netBuf [4]byte
	binary.BigEndian.PutUint32(netBuf[:], networkID)
	salt = append(salt, netBuf[:]...)
	salt = append(salt, deviceMAC[:]...)
	var genBuf [2]byte
	binary.BigEndian.PutUint16(genBuf[:], deviceGen)
	salt = append(salt, genBuf[:]...)

	prk, err := hkdf.Extract(sha256.New, kJoin[:], salt)
	if err != nil {
		return [KeySize]byte{}, fmt.Errorf("hkdf extract failed: %w", err)
	}

	kjReqBytes, err := hkdf.Expand(sha256.New, prk, JoinReqInfo, KeySize)
	if err != nil {
		return [KeySize]byte{}, fmt.Errorf("hkdf expand failed: %w", err)
	}

	var kjReq [KeySize]byte
	copy(kjReq[:], kjReqBytes)
	return kjReq, nil
}

// ComputeHelloProof computes the 16-byte EXPECTED_PROOF over M_HELLO using K_JREQ.
//
// Formula:
//
//	M_HELLO = ASCII("LP2P/V2/M-HELLO") || NETWORK_ID_BE4 || RF_FRAME[0..51]
//	EXPECTED_PROOF = first16(HMAC-SHA256(K_JREQ, M_HELLO))
func ComputeHelloProof(networkID uint32, framePrefix52 []byte, kjReq [KeySize]byte) ([ProofSize]byte, error) {
	if len(framePrefix52) != PrefixFrameLen {
		return [ProofSize]byte{}, fmt.Errorf("%w: frame prefix must be exactly 52 bytes, got %d", ErrInvalidInput, len(framePrefix52))
	}

	mHello := make([]byte, 0, len(JoinHelloTranscriptPrefix)+4+PrefixFrameLen)
	mHello = append(mHello, []byte(JoinHelloTranscriptPrefix)...)
	var netBuf [4]byte
	binary.BigEndian.PutUint32(netBuf[:], networkID)
	mHello = append(mHello, netBuf[:]...)
	mHello = append(mHello, framePrefix52...)

	mac := hmac.New(sha256.New, kjReq[:])
	mac.Write(mHello)
	fullHMAC := mac.Sum(nil)

	var proof [ProofSize]byte
	copy(proof[:], fullHMAC[:ProofSize])
	return proof, nil
}

// VerifyHelloProof verifies the given 16-byte frameProof against the expected proof
// calculated from networkID, deviceMAC, deviceGen, framePrefix52, and kJoin using constant-time comparison.
func VerifyHelloProof(networkID uint32, deviceMAC [6]byte, deviceGen uint16, framePrefix52 []byte, frameProof [ProofSize]byte, kJoin [KeySize]byte) error {
	kjReq, err := DeriveKJReq(networkID, deviceMAC, deviceGen, kJoin)
	if err != nil {
		return err
	}

	expectedProof, err := ComputeHelloProof(networkID, framePrefix52, kjReq)
	if err != nil {
		return err
	}

	if subtle.ConstantTimeCompare(expectedProof[:], frameProof[:]) != 1 {
		return ErrProofMismatch
	}
	return nil
}
