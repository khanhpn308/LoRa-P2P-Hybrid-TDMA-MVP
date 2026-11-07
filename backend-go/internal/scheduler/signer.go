package scheduler

import (
	"crypto/ed25519"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/binary"
	"errors"
	"fmt"
)

var (
	ErrInvalidSignatureLength = errors.New("invalid signature length: Ed25519 signatures must be 64 bytes")
	ErrInvalidPrepareLength   = errors.New("invalid DOWN_SCHED_PREPARE wire frame length: must be exactly 80 bytes")
	ErrInvalidDecisionLength  = errors.New("invalid DOWN_SCHED_DECISION wire frame length: must be exactly 80 bytes")
	ErrInvalidReadyLength     = errors.New("invalid UP_SCHED_READY wire frame length: must be exactly 41 bytes")
	ErrSignatureVerification  = errors.New("ed25519 signature verification failed")
	ErrProofVerification      = errors.New("node UP_SCHED_READY backend proof verification failed")
	ErrInvalidStatus          = errors.New("node reported non-ready status")
	ErrNodeKeyNotFound        = errors.New("node authentication secret key not found in directory")
)

// PrepareTransaction binds the cryptographic parameters of a DOWN_SCHED_PREPARE frame.
type PrepareTransaction struct {
	GatewayNumericID   uint8
	NetworkID          uint32
	ProfileCode        uint8 // 1 for V2-VN920-STATIC-15N
	ScheduleGeneration uint32
	KTarget            uint32 // Planned activation superframe sequence
	KeyID              uint8
	RawFrame           [BytesDownSchedPrepare]byte
	PrepareDigest      [32]byte
}

// DecisionTransaction binds the cryptographic parameters of a DOWN_SCHED_DECISION frame.
type DecisionTransaction struct {
	GatewayNumericID   uint8
	NetworkID          uint32
	ScheduleGeneration uint32
	DecisionType       uint8 // 1 = COMMIT, 0 = ABORT
	KTarget            uint32
	PrepareDigest      [32]byte
	RawFrame           [BytesDownSchedDecision]byte
}

// NodeReadyProofInput captures the extracted fields from UP_SCHED_READY (0x4C).
type NodeReadyProofInput struct {
	NodeID             uint8
	SessionSel         uint8
	FrameCounter       uint32
	ScheduleGeneration uint32
	KTarget            uint32
	Status             uint8
	Reason             uint8
	Proof              [16]byte
}

// NodeKeyDirectory provides access to per-Node root/schedule authentication keys.
type NodeKeyDirectory interface {
	GetNodeAuthKey(nodeID uint8) ([]byte, error)
}

// MapNodeKeyDirectory is a thread-safe map implementation for testing.
type MapNodeKeyDirectory struct {
	keys map[uint8][]byte
}

// NewMapNodeKeyDirectory creates a MapNodeKeyDirectory.
func NewMapNodeKeyDirectory(keys map[uint8][]byte) *MapNodeKeyDirectory {
	cp := make(map[uint8][]byte, len(keys))
	for k, v := range keys {
		buf := make([]byte, len(v))
		copy(buf, v)
		cp[k] = buf
	}
	return &MapNodeKeyDirectory{keys: cp}
}

// GetNodeAuthKey retrieves the secret key for a node.
func (d *MapNodeKeyDirectory) GetNodeAuthKey(nodeID uint8) ([]byte, error) {
	k, ok := d.keys[nodeID]
	if !ok || len(k) == 0 {
		return nil, fmt.Errorf("%w: node %d", ErrNodeKeyNotFound, nodeID)
	}
	return k, nil
}

// ScheduleSigner handles Ed25519 broadcast signing and node ready proof verification.
type ScheduleSigner struct {
	privateKey ed25519.PrivateKey
	publicKey  ed25519.PublicKey
	nodeKeys   NodeKeyDirectory
}

// NewScheduleSigner creates a ScheduleSigner with an Ed25519 keypair and node key directory.
func NewScheduleSigner(priv ed25519.PrivateKey, nodeKeys NodeKeyDirectory) (*ScheduleSigner, error) {
	if len(priv) != ed25519.PrivateKeySize {
		return nil, errors.New("invalid Ed25519 private key size")
	}
	pub := priv.Public().(ed25519.PublicKey)
	return &ScheduleSigner{
		privateKey: priv,
		publicKey:  pub,
		nodeKeys:   nodeKeys,
	}, nil
}

// PublicKey returns the Ed25519 public key.
func (s *ScheduleSigner) PublicKey() ed25519.PublicKey {
	return s.publicKey
}

// SignPrepare constructs and signs an 80-byte DOWN_SCHED_PREPARE broadcast frame (candidate type 0x4B).
// Header (16B): 0x4B | GW_ID:1 | NETWORK_ID:4 | PROFILE_ID:1 | SCHED_GEN:4 | K_TARGET:4 | KEY_ID:1
// Signature (64B): Ed25519 signature over Header16.
func (s *ScheduleSigner) SignPrepare(gwID uint8, netID uint32, profileCode uint8, gen uint32, kTarget uint32, keyID uint8) (*PrepareTransaction, error) {
	var frame [BytesDownSchedPrepare]byte
	header := frame[0:16]

	header[0] = TypeDownSchedPrepare
	header[1] = gwID
	binary.BigEndian.PutUint32(header[2:6], netID)
	header[6] = profileCode
	binary.BigEndian.PutUint32(header[7:11], gen)
	binary.BigEndian.PutUint32(header[11:15], kTarget)
	header[15] = keyID

	sig := ed25519.Sign(s.privateKey, header)
	if len(sig) != 64 {
		return nil, ErrInvalidSignatureLength
	}
	copy(frame[16:80], sig)

	digest := sha256.Sum256(frame[:])

	return &PrepareTransaction{
		GatewayNumericID:   gwID,
		NetworkID:          netID,
		ProfileCode:        profileCode,
		ScheduleGeneration: gen,
		KTarget:            kTarget,
		KeyID:              keyID,
		RawFrame:           frame,
		PrepareDigest:      digest,
	}, nil
}

// VerifyPrepare verifies an 80-byte DOWN_SCHED_PREPARE frame against the public key.
func VerifyPrepare(pub ed25519.PublicKey, frame []byte) (*PrepareTransaction, error) {
	if len(frame) != BytesDownSchedPrepare {
		return nil, ErrInvalidPrepareLength
	}
	if frame[0] != TypeDownSchedPrepare {
		return nil, fmt.Errorf("invalid message type: expected 0x%02x, got 0x%02x", TypeDownSchedPrepare, frame[0])
	}

	header := frame[0:16]
	sig := frame[16:80]

	if !ed25519.Verify(pub, header, sig) {
		return nil, ErrSignatureVerification
	}

	gwID := header[1]
	netID := binary.BigEndian.Uint32(header[2:6])
	profileCode := header[6]
	gen := binary.BigEndian.Uint32(header[7:11])
	kTarget := binary.BigEndian.Uint32(header[11:15])
	keyID := header[15]

	var raw [BytesDownSchedPrepare]byte
	copy(raw[:], frame)
	digest := sha256.Sum256(frame)

	return &PrepareTransaction{
		GatewayNumericID:   gwID,
		NetworkID:          netID,
		ProfileCode:        profileCode,
		ScheduleGeneration: gen,
		KTarget:            kTarget,
		KeyID:              keyID,
		RawFrame:           raw,
		PrepareDigest:      digest,
	}, nil
}

// SignDecision constructs and signs an 80-byte DOWN_SCHED_DECISION frame (candidate type 0x4D).
// Header (16B): 0x4D | GW_ID:1 | NETWORK_ID:4 | SCHED_GEN:4 | DECISION_TYPE:1 | K_TARGET:4 | RESERVED:1
// Signed message: Header16 || PrepareDigest32 (48 bytes cryptographically binding decision to prepare).
// Signature (64B): Ed25519 signature over Header16 || PrepareDigest32.
func (s *ScheduleSigner) SignDecision(gwID uint8, netID uint32, gen uint32, decisionType uint8, kTarget uint32, prepareDigest [32]byte) (*DecisionTransaction, error) {
	var frame [BytesDownSchedDecision]byte
	header := frame[0:16]

	header[0] = TypeDownSchedDecision
	header[1] = gwID
	binary.BigEndian.PutUint32(header[2:6], netID)
	binary.BigEndian.PutUint32(header[6:10], gen)
	header[10] = decisionType
	binary.BigEndian.PutUint32(header[11:15], kTarget)
	header[15] = 0 // Reserved

	// Cryptographically bind to PREPARE: sign header + prepareDigest
	signPayload := make([]byte, 16+32)
	copy(signPayload[0:16], header)
	copy(signPayload[16:48], prepareDigest[:])

	sig := ed25519.Sign(s.privateKey, signPayload)
	if len(sig) != 64 {
		return nil, ErrInvalidSignatureLength
	}
	copy(frame[16:80], sig)

	return &DecisionTransaction{
		GatewayNumericID:   gwID,
		NetworkID:          netID,
		ScheduleGeneration: gen,
		DecisionType:       decisionType,
		KTarget:            kTarget,
		PrepareDigest:      prepareDigest,
		RawFrame:           frame,
	}, nil
}

// VerifyDecision verifies an 80-byte DOWN_SCHED_DECISION frame against PREPARE digest and public key.
func VerifyDecision(pub ed25519.PublicKey, frame []byte, prepareDigest [32]byte) (*DecisionTransaction, error) {
	if len(frame) != BytesDownSchedDecision {
		return nil, ErrInvalidDecisionLength
	}
	if frame[0] != TypeDownSchedDecision {
		return nil, fmt.Errorf("invalid message type: expected 0x%02x, got 0x%02x", TypeDownSchedDecision, frame[0])
	}

	header := frame[0:16]
	sig := frame[16:80]

	signPayload := make([]byte, 16+32)
	copy(signPayload[0:16], header)
	copy(signPayload[16:48], prepareDigest[:])

	if !ed25519.Verify(pub, signPayload, sig) {
		return nil, ErrSignatureVerification
	}

	gwID := header[1]
	netID := binary.BigEndian.Uint32(header[2:6])
	gen := binary.BigEndian.Uint32(header[6:10])
	decType := header[10]
	kTarget := binary.BigEndian.Uint32(header[11:15])

	var raw [BytesDownSchedDecision]byte
	copy(raw[:], frame)

	return &DecisionTransaction{
		GatewayNumericID:   gwID,
		NetworkID:          netID,
		ScheduleGeneration: gen,
		DecisionType:       decType,
		KTarget:            kTarget,
		PrepareDigest:      prepareDigest,
		RawFrame:           raw,
	}, nil
}

// ComputeNodeReadyProof generates the 16-byte HMAC proof for UP_SCHED_READY (0x4C).
// Proof binds: PrepareDigest32 || SchedGen4 || KTarget4 || NodeID1.
func ComputeNodeReadyProof(authKey []byte, prepareDigest [32]byte, schedGen uint32, kTarget uint32, nodeID uint8) [16]byte {
	h := hmac.New(sha256.New, authKey)
	h.Write(prepareDigest[:])

	var buf [9]byte
	binary.BigEndian.PutUint32(buf[0:4], schedGen)
	binary.BigEndian.PutUint32(buf[4:8], kTarget)
	buf[8] = nodeID
	h.Write(buf[:])

	sum := h.Sum(nil)
	var proof [16]byte
	copy(proof[:], sum[0:16])
	return proof
}

// VerifyNodeReadyProof independently checks the 16-byte proof in UP_SCHED_READY.
func (s *ScheduleSigner) VerifyNodeReadyProof(input NodeReadyProofInput, prepareDigest [32]byte) error {
	if input.Status != 1 {
		return fmt.Errorf("%w: status=%d reason=%d", ErrInvalidStatus, input.Status, input.Reason)
	}

	key, err := s.nodeKeys.GetNodeAuthKey(input.NodeID)
	if err != nil {
		return err
	}

	expectedProof := ComputeNodeReadyProof(key, prepareDigest, input.ScheduleGeneration, input.KTarget, input.NodeID)
	if subtle.ConstantTimeCompare(expectedProof[:], input.Proof[:]) != 1 {
		return fmt.Errorf("%w: node %d proof mismatch", ErrProofVerification, input.NodeID)
	}

	return nil
}
