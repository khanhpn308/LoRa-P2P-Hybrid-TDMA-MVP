package session_key_interop

import (
	"encoding/hex"
	"encoding/json"
	"os"
	"testing"
)

type GoldenVectorDoc struct {
	Version        string          `json:"version"`
	SyntheticKeys  SyntheticKeys   `json:"synthetic_keys"`
	PositiveCases  []PositiveCase  `json:"positive_cases"`
	NegativeCases  []NegativeCase  `json:"negative_cases"`
}

type SyntheticKeys struct {
	KGwWrapHex    string `json:"k_gw_wrap_hex"`
	KSessionUpHex string `json:"k_session_up_hex"`
	KSessionDlHex string `json:"k_session_dl_hex"`
	PlaintextHex  string `json:"plaintext_hex"`
	ACKPrkHex     string `json:"ack_prk_hex"`
	KACKHex       string `json:"k_ack_hex"`
}

type PositiveCase struct {
	ID           string            `json:"id"`
	Description  string            `json:"description"`
	Topic        string            `json:"topic"`
	Message      map[string]any    `json:"message"`
	Intermediate map[string]any    `json:"intermediate"`
}

type NegativeCase struct {
	ID             string `json:"id"`
	Description    string `json:"description"`
	TamperTarget   string `json:"tamper_target"`
	ExpectedError  string `json:"expected_error"`
}

func loadGoldenVectors(t *testing.T) GoldenVectorDoc {
	t.Helper()
	data, err := os.ReadFile("session_key_vectors.json")
	if err != nil {
		t.Fatalf("failed to read session_key_vectors.json: %v", err)
	}
	var doc GoldenVectorDoc
	if err := json.Unmarshal(data, &doc); err != nil {
		t.Fatalf("failed to unmarshal golden vectors: %v", err)
	}
	return doc
}

func TestGoldenVector_InstallAAD_And_Wrap(t *testing.T) {
	doc := loadGoldenVectors(t)
	kGwWrap, err := hex.DecodeString(doc.SyntheticKeys.KGwWrapHex)
	if err != nil {
		t.Fatalf("invalid k_gw_wrap_hex: %v", err)
	}
	kSessionUp, err := hex.DecodeString(doc.SyntheticKeys.KSessionUpHex)
	if err != nil {
		t.Fatalf("invalid k_session_up_hex: %v", err)
	}
	kSessionDl, err := hex.DecodeString(doc.SyntheticKeys.KSessionDlHex)
	if err != nil {
		t.Fatalf("invalid k_session_dl_hex: %v", err)
	}

	case1 := doc.PositiveCases[0]
	if case1.ID != "GV-POS-01-INSTALL" {
		t.Fatalf("unexpected case 1 ID: %s", case1.ID)
	}

	msg := case1.Message
	nonceB64 := msg["nonce"].(string)
	nonce, err := DecodeBase64(nonceB64)
	if err != nil {
		t.Fatalf("failed to decode nonce base64: %v", err)
	}

	params := InstallAADParams{
		Topic:                  case1.Topic,
		SchemaVersion:          msg["schema_version"].(string),
		InstallProtocolVersion: uint8(msg["install_protocol_version"].(float64)),
		AADVersion:             uint8(msg["aad_version"].(float64)),
		GatewayID:              msg["gateway_id"].(string),
		TargetGwID:             uint8(msg["target_gw_id"].(float64)),
		DeviceMAC:              msg["device_mac"].(string),
		NodeID:                 uint8(msg["node_id"].(float64)),
		KeyID:                  uint8(msg["key_id"].(float64)),
		SessionID:              msg["session_id"].(string),
		InstallID:              msg["install_id"].(string),
		SessionRevision:        msg["session_revision"].(string),
		AssignmentRevision:     msg["assignment_revision"].(string),
		SessionContextHash:     msg["session_context_hash"].(string),
		NotBefore:              msg["not_before"].(string),
		ExpiresAt:              msg["expires_at"].(string),
		InstallDeadline:        msg["install_deadline"].(string),
		WrapKeyID:              uint32(msg["wrap_key_id"].(float64)),
		CryptoSuite:            msg["crypto_suite"].(string),
		Nonce:                  nonce,
	}

	aad, err := BuildInstallAAD(params)
	if err != nil {
		t.Fatalf("BuildInstallAAD failed: %v", err)
	}

	expectedAADHex := case1.Intermediate["aad_hex"].(string)
	if hex.EncodeToString(aad) != expectedAADHex {
		t.Fatalf("AAD mismatch!\nGot:  %s\nWant: %s", hex.EncodeToString(aad), expectedAADHex)
	}
	if len(aad) != int(case1.Intermediate["aad_len"].(float64)) {
		t.Fatalf("AAD length mismatch: got %d, want %v", len(aad), case1.Intermediate["aad_len"])
	}

	// Producer side: Wrap
	ct, tag, err := WrapSessionKeys(kGwWrap, nonce, kSessionUp, kSessionDl, aad)
	if err != nil {
		t.Fatalf("WrapSessionKeys failed: %v", err)
	}

	expectedCTHex := case1.Intermediate["ciphertext_hex"].(string)
	expectedTagHex := case1.Intermediate["tag_hex"].(string)

	if hex.EncodeToString(ct) != expectedCTHex {
		t.Fatalf("Ciphertext mismatch!\nGot:  %s\nWant: %s", hex.EncodeToString(ct), expectedCTHex)
	}
	if hex.EncodeToString(tag) != expectedTagHex {
		t.Fatalf("Tag mismatch!\nGot:  %s\nWant: %s", hex.EncodeToString(tag), expectedTagHex)
	}

	// Consumer side: Unwrap
	decUp, decDl, err := UnwrapSessionKeys(kGwWrap, nonce, ct, tag, aad)
	if err != nil {
		t.Fatalf("UnwrapSessionKeys failed: %v", err)
	}
	if hex.EncodeToString(decUp) != doc.SyntheticKeys.KSessionUpHex {
		t.Fatalf("Decrypted K_SESSION_UP mismatch: %s", hex.EncodeToString(decUp))
	}
	if hex.EncodeToString(decDl) != doc.SyntheticKeys.KSessionDlHex {
		t.Fatalf("Decrypted K_SESSION_DL mismatch: %s", hex.EncodeToString(decDl))
	}
}

func TestGoldenVector_ACK_Installed(t *testing.T) {
	doc := loadGoldenVectors(t)
	kGwWrap, err := hex.DecodeString(doc.SyntheticKeys.KGwWrapHex)
	if err != nil {
		t.Fatalf("invalid k_gw_wrap_hex: %v", err)
	}

	case2 := doc.PositiveCases[1]
	if case2.ID != "GV-POS-02-ACK-INSTALLED" {
		t.Fatalf("unexpected case 2 ID: %s", case2.ID)
	}

	msg := case2.Message
	wrapKeyID := uint32(msg["wrap_key_id"].(float64))
	gwID := msg["gateway_id"].(string)

	// Derive K_ACK
	kAck, err := DeriveKACK(kGwWrap, wrapKeyID, gwID)
	if err != nil {
		t.Fatalf("DeriveKACK failed: %v", err)
	}
	if hex.EncodeToString(kAck) != doc.SyntheticKeys.KACKHex {
		t.Fatalf("K_ACK mismatch!\nGot:  %s\nWant: %s", hex.EncodeToString(kAck), doc.SyntheticKeys.KACKHex)
	}

	// Build M_ACK
	params := ACKTranscriptParams{
		Topic:              case2.Topic,
		SchemaVersion:      msg["schema_version"].(string),
		ACKProtocolVersion: uint8(msg["ack_protocol_version"].(float64)),
		GatewayID:          gwID,
		InstallID:          msg["install_id"].(string),
		SessionID:          msg["session_id"].(string),
		SessionRevision:    msg["session_revision"].(string),
		WrapKeyID:          wrapKeyID,
		Status:             msg["status"].(string),
		ReasonCode:         msg["reason_code"].(string),
	}

	mAck, err := BuildACKTranscript(params)
	if err != nil {
		t.Fatalf("BuildACKTranscript failed: %v", err)
	}

	expectedMAckHex := case2.Intermediate["m_ack_hex"].(string)
	if hex.EncodeToString(mAck) != expectedMAckHex {
		t.Fatalf("M_ACK mismatch!\nGot:  %s\nWant: %s", hex.EncodeToString(mAck), expectedMAckHex)
	}
	if len(mAck) != int(case2.Intermediate["m_ack_len"].(float64)) {
		t.Fatalf("M_ACK length mismatch: got %d, want %v", len(mAck), case2.Intermediate["m_ack_len"])
	}

	// Compute & verify ACK tag
	tag, err := ComputeACKTag(kAck, mAck)
	if err != nil {
		t.Fatalf("ComputeACKTag failed: %v", err)
	}

	expectedTagHex := case2.Intermediate["ack_tag_hex"].(string)
	if hex.EncodeToString(tag) != expectedTagHex {
		t.Fatalf("ACK tag mismatch!\nGot:  %s\nWant: %s", hex.EncodeToString(tag), expectedTagHex)
	}

	if err := VerifyACKTag(kAck, mAck, tag); err != nil {
		t.Fatalf("VerifyACKTag failed on authentic tag: %v", err)
	}
}

func TestGoldenVector_ACK_Rejected(t *testing.T) {
	doc := loadGoldenVectors(t)
	kGwWrap, err := hex.DecodeString(doc.SyntheticKeys.KGwWrapHex)
	if err != nil {
		t.Fatalf("invalid k_gw_wrap_hex: %v", err)
	}

	case3 := doc.PositiveCases[2]
	if case3.ID != "GV-POS-03-ACK-REJECTED" {
		t.Fatalf("unexpected case 3 ID: %s", case3.ID)
	}

	msg := case3.Message
	wrapKeyID := uint32(msg["wrap_key_id"].(float64))
	gwID := msg["gateway_id"].(string)

	kAck, err := DeriveKACK(kGwWrap, wrapKeyID, gwID)
	if err != nil {
		t.Fatalf("DeriveKACK failed: %v", err)
	}

	params := ACKTranscriptParams{
		Topic:              case3.Topic,
		SchemaVersion:      msg["schema_version"].(string),
		ACKProtocolVersion: uint8(msg["ack_protocol_version"].(float64)),
		GatewayID:          gwID,
		InstallID:          msg["install_id"].(string),
		SessionID:          msg["session_id"].(string),
		SessionRevision:    msg["session_revision"].(string),
		WrapKeyID:          wrapKeyID,
		Status:             msg["status"].(string),
		ReasonCode:         msg["reason_code"].(string),
	}

	mAck, err := BuildACKTranscript(params)
	if err != nil {
		t.Fatalf("BuildACKTranscript failed: %v", err)
	}

	expectedMAckHex := case3.Intermediate["m_ack_hex"].(string)
	if hex.EncodeToString(mAck) != expectedMAckHex {
		t.Fatalf("M_ACK mismatch for REJECTED: %s", hex.EncodeToString(mAck))
	}

	tag, err := ComputeACKTag(kAck, mAck)
	if err != nil {
		t.Fatalf("ComputeACKTag failed: %v", err)
	}

	expectedTagHex := case3.Intermediate["ack_tag_hex"].(string)
	if hex.EncodeToString(tag) != expectedTagHex {
		t.Fatalf("ACK tag mismatch for REJECTED: %s", hex.EncodeToString(tag))
	}

	if err := VerifyACKTag(kAck, mAck, tag); err != nil {
		t.Fatalf("VerifyACKTag failed on valid REJECTED tag: %v", err)
	}
}

func TestNegativeCases_AESGCM_FailClosed(t *testing.T) {
	doc := loadGoldenVectors(t)
	kGwWrap, _ := hex.DecodeString(doc.SyntheticKeys.KGwWrapHex)
	case1 := doc.PositiveCases[0]
	msg := case1.Message
	nonce, _ := DecodeBase64(msg["nonce"].(string))
	ct, _ := hex.DecodeString(case1.Intermediate["ciphertext_hex"].(string))
	tag, _ := hex.DecodeString(case1.Intermediate["tag_hex"].(string))
	aad, _ := hex.DecodeString(case1.Intermediate["aad_hex"].(string))

	// Baseline unwrap must pass
	_, _, err := UnwrapSessionKeys(kGwWrap, nonce, ct, tag, aad)
	if err != nil {
		t.Fatalf("baseline unwrap failed: %v", err)
	}

	// 1. Tampered ciphertext (1 bit flip)
	tamperedCT := append([]byte(nil), ct...)
	tamperedCT[0] ^= 0x01
	_, _, err = UnwrapSessionKeys(kGwWrap, nonce, tamperedCT, tag, aad)
	if err == nil {
		t.Errorf("GV-NEG-01: unwrap should fail on tampered ciphertext")
	}

	// 2. Tampered tag (1 bit flip)
	tamperedTag := append([]byte(nil), tag...)
	tamperedTag[15] ^= 0x01
	_, _, err = UnwrapSessionKeys(kGwWrap, nonce, ct, tamperedTag, aad)
	if err == nil {
		t.Errorf("GV-NEG-02: unwrap should fail on tampered tag")
	}

	// 3. Wrong wrap key
	wrongKey := append([]byte(nil), kGwWrap...)
	wrongKey[0] ^= 0xFF
	_, _, err = UnwrapSessionKeys(wrongKey, nonce, ct, tag, aad)
	if err == nil {
		t.Errorf("GV-NEG-03: unwrap should fail on wrong wrap key")
	}

	// 4. Tampered AAD (topic modified)
	tamperedAAD := append([]byte(nil), aad...)
	tamperedAAD[len(tamperedAAD)-1] ^= 0x01
	_, _, err = UnwrapSessionKeys(kGwWrap, nonce, ct, tag, tamperedAAD)
	if err == nil {
		t.Errorf("GV-NEG-04: unwrap should fail on tampered AAD")
	}

	// 5. Truncated ciphertext
	_, _, err = UnwrapSessionKeys(kGwWrap, nonce, ct[:63], tag, aad)
	if err == nil {
		t.Errorf("GV-NEG-12: unwrap should fail on truncated ciphertext")
	}

	// 6. Truncated tag
	_, _, err = UnwrapSessionKeys(kGwWrap, nonce, ct, tag[:15], aad)
	if err == nil {
		t.Errorf("unwrap should fail on truncated tag")
	}
}

func TestNegativeCases_ACK_FailClosed(t *testing.T) {
	doc := loadGoldenVectors(t)
	kGwWrap, _ := hex.DecodeString(doc.SyntheticKeys.KGwWrapHex)
	case2 := doc.PositiveCases[1]
	msg := case2.Message
	wrapKeyID := uint32(msg["wrap_key_id"].(float64))
	gwID := msg["gateway_id"].(string)

	kAck, _ := DeriveKACK(kGwWrap, wrapKeyID, gwID)
	mAck, _ := hex.DecodeString(case2.Intermediate["m_ack_hex"].(string))
	tag, _ := hex.DecodeString(case2.Intermediate["ack_tag_hex"].(string))

	// Baseline verify must pass
	if err := VerifyACKTag(kAck, mAck, tag); err != nil {
		t.Fatalf("baseline ACK verify failed: %v", err)
	}

	// 1. Tampered ACK tag
	tamperedTag := append([]byte(nil), tag...)
	tamperedTag[0] ^= 0x01
	if err := VerifyACKTag(kAck, mAck, tamperedTag); err == nil {
		t.Errorf("GV-NEG-09: verification should fail on tampered ACK tag")
	}

	// 2. Tampered transcript
	tamperedMAck := append([]byte(nil), mAck...)
	tamperedMAck[len(tamperedMAck)-1] ^= 0x01
	if err := VerifyACKTag(kAck, tamperedMAck, tag); err == nil {
		t.Errorf("GV-NEG-10: verification should fail on tampered M_ACK transcript")
	}

	// 3. Truncated ACK tag
	if err := VerifyACKTag(kAck, mAck, tag[:15]); err == nil {
		t.Errorf("verification should fail on truncated tag")
	}
}
