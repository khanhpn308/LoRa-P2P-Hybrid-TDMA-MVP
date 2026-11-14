package api

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var (
	macRegex = regexp.MustCompile(`^[0-9a-f]{12}$`)
)

// KeyWrapper abstracts AEAD wrapping of root device provisioning keys.
type KeyWrapper interface {
	Wrap(plaintext []byte) ([]byte, error)
}

// AESGCMKeyWrapper implements KeyWrapper using AES-256-GCM.
type AESGCMKeyWrapper struct {
	masterKey [32]byte
}

// NewAESGCMKeyWrapper constructs a new AESGCMKeyWrapper from a 256-bit master key.
func NewAESGCMKeyWrapper(masterKey [32]byte) *AESGCMKeyWrapper {
	return &AESGCMKeyWrapper{masterKey: masterKey}
}

// Wrap encrypts plaintext with AES-256-GCM using a unique 12-byte CSPRNG nonce.
// Envelope format: nonce (12 bytes) || ciphertext + tag (len(plaintext) + 16 bytes).
func (w *AESGCMKeyWrapper) Wrap(plaintext []byte) ([]byte, error) {
	block, err := aes.NewCipher(w.masterKey[:])
	if err != nil {
		return nil, fmt.Errorf("aes cipher error: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm error: %w", err)
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, fmt.Errorf("failed to generate random nonce: %w", err)
	}

	ciphertext := gcm.Seal(nil, nonce, plaintext, nil)
	wrapped := make([]byte, 0, len(nonce)+len(ciphertext))
	wrapped = append(wrapped, nonce...)
	wrapped = append(wrapped, ciphertext...)
	return wrapped, nil
}

// Unwrap decrypts the wrapped ciphertext and verifies the GCM authentication tag.
func (w *AESGCMKeyWrapper) Unwrap(wrapped []byte) ([]byte, error) {
	block, err := aes.NewCipher(w.masterKey[:])
	if err != nil {
		return nil, fmt.Errorf("aes cipher error: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm error: %w", err)
	}
	nonceSize := gcm.NonceSize()
	if len(wrapped) < nonceSize+16 {
		return nil, errors.New("wrapped key payload too short")
	}
	nonce := wrapped[:nonceSize]
	ciphertext := wrapped[nonceSize:]
	return gcm.Open(nil, nonce, ciphertext, nil)
}

// DeviceProvisionRequestDTO matches the DeviceProvisionRequest component schema in openapi.yaml.
type DeviceProvisionRequestDTO struct {
	NetworkID          uint64  `json:"network_id"`
	DeviceMAC          string  `json:"device_mac"`
	KJoin              string  `json:"k_join"`
	Generation         *uint16 `json:"generation,omitempty"`
	InitialJoinCounter *uint32 `json:"initial_join_counter,omitempty"`
}

// DeviceProvisionResponseDTO matches the DeviceProvisionResponse component schema in openapi.yaml.
type DeviceProvisionResponseDTO struct {
	DeviceMAC  string `json:"device_mac"`
	NetworkID  uint64 `json:"network_id"`
	Generation uint16 `json:"generation"`
	Status     string `json:"status"`
	CreatedAt  string `json:"created_at"`
}

// ProvisionHandler handles device registration and K_JOIN provisioning REST endpoints.
type ProvisionHandler struct {
	repo          storage.ProvisionRepository
	keyWrapper    KeyWrapper
	authenticator Authenticator
}

// NewProvisionHandler constructs a new ProvisionHandler.
func NewProvisionHandler(repo storage.ProvisionRepository, keyWrapper KeyWrapper, auth Authenticator) *ProvisionHandler {
	return &ProvisionHandler{
		repo:          repo,
		keyWrapper:    keyWrapper,
		authenticator: auth,
	}
}

// RegisterRoutes registers the device provisioning route on http.ServeMux according to OpenAPI 3.0.3 spec.
func (h *ProvisionHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v1/devices/provision", h.handleProvision)
}

func (h *ProvisionHandler) handleProvision(w http.ResponseWriter, r *http.Request) {
	// 1. RBAC authorization check (SE-004)
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "bearer token required")
		return
	}

	token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
	if token == "" {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "empty bearer token")
		return
	}

	if h.authenticator == nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "authenticator unconfigured")
		return
	}

	role, err := h.authenticator.Authenticate(token)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "invalid or expired bearer token")
		return
	}

	if role != RoleAdmin {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "role ADMIN required for device provisioning")
		return
	}

	// 2. Read and strictly decode request JSON body (jsonboundary / SE-002)
	body, err := io.ReadAll(io.LimitReader(r.Body, maxPayloadBytes+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "failed to read request body")
		return
	}

	var dto DeviceProvisionRequestDTO
	if err := jsonboundary.DecodeObject(body, maxPayloadBytes, &dto); err != nil {
		writeError(w, http.StatusBadRequest, "MALFORMED_JSON", err.Error())
		return
	}

	// 3. Strict field validations
	if dto.NetworkID == 0 {
		writeError(w, http.StatusBadRequest, "INVALID_NETWORK_ID", "network_id must be a positive integer")
		return
	}

	mac := strings.TrimSpace(dto.DeviceMAC)
	if !macRegex.MatchString(mac) {
		writeError(w, http.StatusBadRequest, "INVALID_DEVICE_MAC", "device_mac must be exactly 12 lowercase hexadecimal characters")
		return
	}

	macBytes, err := hex.DecodeString(mac)
	if err != nil || len(macBytes) != 6 {
		writeError(w, http.StatusBadRequest, "INVALID_DEVICE_MAC", "invalid hex encoding for device_mac")
		return
	}
	var devMAC [6]byte
	copy(devMAC[:], macBytes)

	// Validate K_JOIN format and decode to exact 32-byte secret
	rawKJoin, err := parseKJoin(dto.KJoin)
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_K_JOIN", err.Error())
		return
	}
	// Zeroize rawKJoin buffer on exit
	defer func() {
		for i := range rawKJoin {
			rawKJoin[i] = 0
		}
	}()

	gen := uint16(1)
	if dto.Generation != nil {
		if *dto.Generation < 1 {
			writeError(w, http.StatusBadRequest, "INVALID_GENERATION", "generation must be >= 1")
			return
		}
		gen = *dto.Generation
	}

	initialCounter := uint32(0)
	if dto.InitialJoinCounter != nil {
		initialCounter = *dto.InitialJoinCounter
	}

	// 4. Wrap raw K_JOIN with Backend Master Key using AES-256-GCM (SE-007)
	if h.keyWrapper == nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "key wrapper unconfigured")
		return
	}

	wrappedKey, err := h.keyWrapper.Wrap(rawKJoin[:])
	if err != nil {
		writeError(w, http.StatusInternalServerError, "KEY_WRAP_ERROR", "failed to wrap key material")
		return
	}

	// 5. Atomic database insertion
	input := &storage.ProvisionDeviceInput{
		NetworkID:          uint32(dto.NetworkID),
		DeviceMAC:          devMAC,
		Generation:         gen,
		KJoinWrapped:       wrappedKey,
		InitialJoinCounter: initialCounter,
	}

	result, err := h.repo.ProvisionDevice(r.Context(), input)
	if err != nil {
		switch {
		case errors.Is(err, storage.ErrDeviceAlreadyProvisioned), errors.Is(err, storage.ErrGenerationAlreadyExists):
			writeError(w, http.StatusConflict, "CONFLICT", err.Error())
		case errors.Is(err, storage.ErrInvalidProvisionInput):
			writeError(w, http.StatusBadRequest, "INVALID_INPUT", err.Error())
		case errors.Is(err, storage.ErrDeviceNotActive):
			writeError(w, http.StatusConflict, "DEVICE_NOT_ACTIVE", err.Error())
		default:
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to provision device")
		}
		return
	}

	// 6. Audit logging (SE-003: NEVER log secret material or wrapped keys)
	log.Printf("device provisioned successfully: network_id=%d device_mac=%s generation=%d",
		result.NetworkID, mac, result.Generation)

	// 7. Write HTTP 201 response (never echoing K_JOIN)
	resp := DeviceProvisionResponseDTO{
		DeviceMAC:  mac,
		NetworkID:  uint64(result.NetworkID),
		Generation: result.Generation,
		Status:     result.Status,
		CreatedAt:  result.CreatedAt.UTC().Format(time.RFC3339),
	}

	writeJSON(w, http.StatusCreated, resp)
}

func parseKJoin(raw string) ([32]byte, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return [32]byte{}, errors.New("k_join cannot be empty")
	}

	var keyBytes []byte
	var err error

	if len(trimmed) == 64 && isHexString(trimmed) {
		keyBytes, err = hex.DecodeString(trimmed)
		if err != nil {
			return [32]byte{}, fmt.Errorf("invalid hex encoding: %w", err)
		}
	} else {
		// Attempt standard Base64, then URL Base64 (with and without padding)
		keyBytes, err = base64.StdEncoding.DecodeString(trimmed)
		if err != nil {
			keyBytes, err = base64.URLEncoding.DecodeString(trimmed)
		}
		if err != nil {
			keyBytes, err = base64.RawStdEncoding.DecodeString(trimmed)
		}
		if err != nil {
			keyBytes, err = base64.RawURLEncoding.DecodeString(trimmed)
		}
		if err != nil {
			return [32]byte{}, fmt.Errorf("k_join must be 64 hex characters or 32-byte Base64: %w", err)
		}
	}

	if len(keyBytes) != 32 {
		zeroize(keyBytes)
		return [32]byte{}, fmt.Errorf("k_join must decode to exactly 32 bytes, got %d", len(keyBytes))
	}

	var kJoin [32]byte
	copy(kJoin[:], keyBytes)
	zeroize(keyBytes)
	return kJoin, nil
}

func isHexString(s string) bool {
	for i := 0; i < len(s); i++ {
		c := s[i]
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')) {
			return false
		}
	}
	return true
}

func zeroize(b []byte) {
	for i := range b {
		b[i] = 0
	}
}
