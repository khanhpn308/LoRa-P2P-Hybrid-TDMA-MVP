package session_key_interop

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hkdf"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

var (
	ErrInvalidKeySize    = errors.New("invalid key size: K_GW_WRAP must be 32 bytes")
	ErrInvalidNonceSize  = errors.New("invalid nonce size: must be 12 bytes")
	ErrInvalidPlaintext  = errors.New("invalid plaintext: must be 64 bytes (K_SESSION_UP[32] || K_SESSION_DL[32])")
	ErrInvalidCiphertext = errors.New("invalid ciphertext: must be 64 bytes")
	ErrInvalidTagSize    = errors.New("invalid tag size: must be 16 bytes")
	ErrTagVerification   = errors.New("AES-GCM tag verification failed (authentication failure)")
	ErrACKTagMismatch    = errors.New("ACK HMAC tag mismatch (constant-time verification failed)")
	ErrInvalidTimestamp  = errors.New("invalid RFC3339 UTC timestamp")
	ErrInvalidMAC        = errors.New("invalid MAC address: must be 12 lowercase hex characters")
	ErrInvalidSHA256     = errors.New("invalid SHA256 hex: must be 64 lowercase hex characters")
	ErrInvalidUUID       = errors.New("invalid canonical lowercase UUID")
	ErrStringTooLong     = errors.New("string length exceeds 65535 bytes for LP encoding")
)

const (
	KeyWrapSize   = 32
	NonceSize     = 12
	SessionKeyLen = 32
	PlaintextSize = 64
	TagSize       = 16
	ACKTagSize    = 16

	InstallAADPrefix = "LP2P/MQTT/V1/KEY-INSTALL"
	ACKSaltPrefix    = "LP2P/MQTT/V1/ACK-SALT"
	ACKInfoPrefix    = "LP2P/MQTT/V1/KEY-INSTALL-ACK"
	ACKTranscriptPrefix = "LP2P/MQTT/V1/M-ACK"
)

// InstallAADParams holds all fields required to build the canonical Install AAD V1.
type InstallAADParams struct {
	Topic                  string
	SchemaVersion          string
	InstallProtocolVersion uint8
	AADVersion             uint8
	GatewayID              string
	TargetGwID             uint8
	DeviceMAC              string // 12 hex chars
	NodeID                 uint8
	KeyID                  uint8
	SessionID              string // UUID
	InstallID              string // UUID
	SessionRevision        string // decimal uint64
	AssignmentRevision     string // decimal uint64
	SessionContextHash     string // 64 hex chars
	NotBefore              string // RFC3339 UTC
	ExpiresAt              string // RFC3339 UTC
	InstallDeadline        string // RFC3339 UTC
	WrapKeyID              uint32
	CryptoSuite            string
	Nonce                  []byte // 12 bytes
}

// ACKTranscriptParams holds all fields required to build the canonical ACK transcript M_ACK V1.
type ACKTranscriptParams struct {
	Topic              string
	SchemaVersion      string
	ACKProtocolVersion uint8
	GatewayID          string
	InstallID          string // UUID
	SessionID          string // UUID
	SessionRevision    string // decimal uint64
	WrapKeyID          uint32
	Status             string
	ReasonCode         string
}

// lp encodes length-prefixed string: U16(len) || UTF-8 bytes.
func lp(s string) ([]byte, error) {
	b := []byte(s)
	if len(b) > 65535 {
		return nil, ErrStringTooLong
	}
	out := make([]byte, 2+len(b))
	binary.BigEndian.PutUint16(out[0:2], uint16(len(b)))
	copy(out[2:], b)
	return out, nil
}

// parseTimeMS converts RFC3339 UTC string with 'Z' suffix to Unix epoch milliseconds uint64 big-endian.
func parseTimeMS(s string) ([]byte, error) {
	if !strings.HasSuffix(s, "Z") {
		return nil, ErrInvalidTimestamp
	}
	t, err := time.Parse(time.RFC3339Nano, s)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidTimestamp, err)
	}
	ms := uint64(t.UnixMilli())
	out := make([]byte, 8)
	binary.BigEndian.PutUint64(out, ms)
	return out, nil
}

// parseUUID converts a canonical lowercase UUID string (e.g. "550e8400-e29b-41d4-a716-446655440000") into 16 network-order bytes.
func parseUUID(s string) ([]byte, error) {
	if len(s) != 36 {
		return nil, ErrInvalidUUID
	}
	if s[8] != '-' || s[13] != '-' || s[18] != '-' || s[23] != '-' {
		return nil, ErrInvalidUUID
	}
	clean := s[0:8] + s[9:13] + s[14:18] + s[19:23] + s[24:36]
	for i := 0; i < len(clean); i++ {
		c := clean[i]
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
			return nil, ErrInvalidUUID
		}
	}
	b, err := hex.DecodeString(clean)
	if err != nil || len(b) != 16 {
		return nil, ErrInvalidUUID
	}
	return b, nil
}

// BuildInstallAAD constructs the exact canonical binary AAD for Install V1.
func BuildInstallAAD(params InstallAADParams) ([]byte, error) {
	if len(params.Nonce) != NonceSize {
		return nil, ErrInvalidNonceSize
	}

	prefixBytes, err := lp(InstallAADPrefix)
	if err != nil {
		return nil, err
	}
	topicBytes, err := lp(params.Topic)
	if err != nil {
		return nil, err
	}
	schemaBytes, err := lp(params.SchemaVersion)
	if err != nil {
		return nil, err
	}
	gwIDBytes, err := lp(params.GatewayID)
	if err != nil {
		return nil, err
	}

	macBytes, err := hex.DecodeString(params.DeviceMAC)
	if err != nil || len(macBytes) != 6 {
		return nil, ErrInvalidMAC
	}

	sessionUUID, err := parseUUID(params.SessionID)
	if err != nil {
		return nil, err
	}
	installUUID, err := parseUUID(params.InstallID)
	if err != nil {
		return nil, err
	}

	sessRev, err := strconv.ParseUint(params.SessionRevision, 10, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid session_revision uint64: %w", err)
	}
	assignRev, err := strconv.ParseUint(params.AssignmentRevision, 10, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid assignment_revision uint64: %w", err)
	}

	hashBytes, err := hex.DecodeString(params.SessionContextHash)
	if err != nil || len(hashBytes) != 32 {
		return nil, ErrInvalidSHA256
	}

	notBeforeBytes, err := parseTimeMS(params.NotBefore)
	if err != nil {
		return nil, err
	}
	expiresAtBytes, err := parseTimeMS(params.ExpiresAt)
	if err != nil {
		return nil, err
	}
	deadlineBytes, err := parseTimeMS(params.InstallDeadline)
	if err != nil {
		return nil, err
	}

	suiteBytes, err := lp(params.CryptoSuite)
	if err != nil {
		return nil, err
	}

	var buf []byte
	buf = append(buf, prefixBytes...)
	buf = append(buf, topicBytes...)
	buf = append(buf, schemaBytes...)
	buf = append(buf, params.InstallProtocolVersion)
	buf = append(buf, params.AADVersion)
	buf = append(buf, gwIDBytes...)
	buf = append(buf, params.TargetGwID)
	buf = append(buf, macBytes...)
	buf = append(buf, params.NodeID)
	buf = append(buf, params.KeyID)
	buf = append(buf, sessionUUID...)
	buf = append(buf, installUUID...)

	var u64Buf [8]byte
	binary.BigEndian.PutUint64(u64Buf[:], sessRev)
	buf = append(buf, u64Buf[:]...)

	binary.BigEndian.PutUint64(u64Buf[:], assignRev)
	buf = append(buf, u64Buf[:]...)

	buf = append(buf, hashBytes...)
	buf = append(buf, notBeforeBytes...)
	buf = append(buf, expiresAtBytes...)
	buf = append(buf, deadlineBytes...)

	var u32Buf [4]byte
	binary.BigEndian.PutUint32(u32Buf[:], params.WrapKeyID)
	buf = append(buf, u32Buf[:]...)

	buf = append(buf, suiteBytes...)
	buf = append(buf, params.Nonce...)

	return buf, nil
}

// WrapSessionKeys performs AES-256-GCM encryption of K_SESSION_UP || K_SESSION_DL.
// Returns 64-byte ciphertext and 16-byte authentication tag.
func WrapSessionKeys(kGwWrap, nonce, kSessionUp, kSessionDl, aad []byte) ([]byte, []byte, error) {
	if len(kGwWrap) != KeyWrapSize {
		return nil, nil, ErrInvalidKeySize
	}
	if len(nonce) != NonceSize {
		return nil, nil, ErrInvalidNonceSize
	}
	if len(kSessionUp) != SessionKeyLen || len(kSessionDl) != SessionKeyLen {
		return nil, nil, ErrInvalidPlaintext
	}

	plaintext := make([]byte, 0, PlaintextSize)
	plaintext = append(plaintext, kSessionUp...)
	plaintext = append(plaintext, kSessionDl...)

	block, err := aes.NewCipher(kGwWrap)
	if err != nil {
		return nil, nil, fmt.Errorf("aes.NewCipher failed: %w", err)
	}

	gcm, err := cipher.NewGCMWithNonceSize(block, NonceSize)
	if err != nil {
		return nil, nil, fmt.Errorf("cipher.NewGCM failed: %w", err)
	}

	// gcm.Seal appends tag to ciphertext
	sealed := gcm.Seal(nil, nonce, plaintext, aad)
	if len(sealed) != PlaintextSize+TagSize {
		return nil, nil, fmt.Errorf("unexpected sealed length: %d", len(sealed))
	}

	ciphertext := sealed[:PlaintextSize]
	tag := sealed[PlaintextSize:]
	return ciphertext, tag, nil
}

// UnwrapSessionKeys performs AES-256-GCM decryption and tag verification.
// Returns verified K_SESSION_UP (32B) and K_SESSION_DL (32B), or error on authentication failure.
func UnwrapSessionKeys(kGwWrap, nonce, ciphertext, tag, aad []byte) ([]byte, []byte, error) {
	if len(kGwWrap) != KeyWrapSize {
		return nil, nil, ErrInvalidKeySize
	}
	if len(nonce) != NonceSize {
		return nil, nil, ErrInvalidNonceSize
	}
	if len(ciphertext) != PlaintextSize {
		return nil, nil, ErrInvalidCiphertext
	}
	if len(tag) != TagSize {
		return nil, nil, ErrInvalidTagSize
	}

	block, err := aes.NewCipher(kGwWrap)
	if err != nil {
		return nil, nil, fmt.Errorf("aes.NewCipher failed: %w", err)
	}

	gcm, err := cipher.NewGCMWithNonceSize(block, NonceSize)
	if err != nil {
		return nil, nil, fmt.Errorf("cipher.NewGCM failed: %w", err)
	}

	sealed := make([]byte, 0, len(ciphertext)+len(tag))
	sealed = append(sealed, ciphertext...)
	sealed = append(sealed, tag...)

	plaintext, err := gcm.Open(nil, nonce, sealed, aad)
	if err != nil {
		return nil, nil, ErrTagVerification
	}

	if len(plaintext) != PlaintextSize {
		return nil, nil, ErrInvalidPlaintext
	}

	kSessionUp := make([]byte, SessionKeyLen)
	kSessionDl := make([]byte, SessionKeyLen)
	copy(kSessionUp, plaintext[:SessionKeyLen])
	copy(kSessionDl, plaintext[SessionKeyLen:])
	return kSessionUp, kSessionDl, nil
}

// DeriveKACK derives the 32-byte HMAC key for session key ACKs using HKDF-SHA256.
//
//	ACK_PRK = HKDF-Extract(salt=ASCII("LP2P/MQTT/V1/ACK-SALT"), IKM=K_GW_WRAP)
//	K_ACK = HKDF-Expand(ACK_PRK, LP("LP2P/MQTT/V1/KEY-INSTALL-ACK") || U32(wrap_key_id) || LP(gateway_id), 32)
func DeriveKACK(kGwWrap []byte, wrapKeyID uint32, gatewayID string) ([]byte, error) {
	if len(kGwWrap) != KeyWrapSize {
		return nil, ErrInvalidKeySize
	}

	salt := []byte(ACKSaltPrefix)
	prk, err := hkdf.Extract(sha256.New, kGwWrap, salt)
	if err != nil {
		return nil, fmt.Errorf("hkdf.Extract failed: %w", err)
	}

	prefixBytes, err := lp(ACKInfoPrefix)
	if err != nil {
		return nil, err
	}
	gwIDBytes, err := lp(gatewayID)
	if err != nil {
		return nil, err
	}

	var info []byte
	info = append(info, prefixBytes...)
	var u32Buf [4]byte
	binary.BigEndian.PutUint32(u32Buf[:], wrapKeyID)
	info = append(info, u32Buf[:]...)
	info = append(info, gwIDBytes...)

	kAck, err := hkdf.Expand(sha256.New, prk, string(info), 32)
	if err != nil {
		return nil, fmt.Errorf("hkdf.Expand failed: %w", err)
	}

	return kAck, nil
}

// BuildACKTranscript constructs the exact canonical binary ACK transcript M_ACK V1.
func BuildACKTranscript(params ACKTranscriptParams) ([]byte, error) {
	prefixBytes, err := lp(ACKTranscriptPrefix)
	if err != nil {
		return nil, err
	}
	topicBytes, err := lp(params.Topic)
	if err != nil {
		return nil, err
	}
	schemaBytes, err := lp(params.SchemaVersion)
	if err != nil {
		return nil, err
	}
	gwIDBytes, err := lp(params.GatewayID)
	if err != nil {
		return nil, err
	}

	installUUID, err := parseUUID(params.InstallID)
	if err != nil {
		return nil, err
	}
	sessionUUID, err := parseUUID(params.SessionID)
	if err != nil {
		return nil, err
	}

	sessRev, err := strconv.ParseUint(params.SessionRevision, 10, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid session_revision uint64: %w", err)
	}

	statusBytes, err := lp(params.Status)
	if err != nil {
		return nil, err
	}
	reasonBytes, err := lp(params.ReasonCode)
	if err != nil {
		return nil, err
	}

	var buf []byte
	buf = append(buf, prefixBytes...)
	buf = append(buf, topicBytes...)
	buf = append(buf, schemaBytes...)
	buf = append(buf, params.ACKProtocolVersion)
	buf = append(buf, gwIDBytes...)
	buf = append(buf, installUUID...)
	buf = append(buf, sessionUUID...)

	var u64Buf [8]byte
	binary.BigEndian.PutUint64(u64Buf[:], sessRev)
	buf = append(buf, u64Buf[:]...)

	var u32Buf [4]byte
	binary.BigEndian.PutUint32(u32Buf[:], params.WrapKeyID)
	buf = append(buf, u32Buf[:]...)

	buf = append(buf, statusBytes...)
	buf = append(buf, reasonBytes...)

	return buf, nil
}

// ComputeACKTag computes the 16-byte truncated HMAC-SHA256 tag over M_ACK.
func ComputeACKTag(kAck, mAck []byte) ([]byte, error) {
	if len(kAck) != 32 {
		return nil, ErrInvalidKeySize
	}
	mac := hmac.New(sha256.New, kAck)
	mac.Write(mAck)
	fullHMAC := mac.Sum(nil)
	tag := make([]byte, ACKTagSize)
	copy(tag, fullHMAC[:ACKTagSize])
	return tag, nil
}

// VerifyACKTag performs constant-time comparison between expected ACK tag and received tag.
func VerifyACKTag(kAck, mAck, receivedTag []byte) error {
	if len(receivedTag) != ACKTagSize {
		return ErrInvalidTagSize
	}
	expectedTag, err := ComputeACKTag(kAck, mAck)
	if err != nil {
		return err
	}
	if subtle.ConstantTimeCompare(expectedTag, receivedTag) != 1 {
		return ErrACKTagMismatch
	}
	return nil
}

// Helper for Base64 standard decoding
func DecodeBase64(s string) ([]byte, error) {
	return base64.StdEncoding.DecodeString(s)
}

// Helper for Base64 standard encoding
func EncodeBase64(b []byte) string {
	return base64.StdEncoding.EncodeToString(b)
}
