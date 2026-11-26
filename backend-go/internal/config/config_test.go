package config_test

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/pem"
	"errors"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/config"
)

func TestLoad_Defaults(t *testing.T) {
	// Empty environment
	cfg := config.LoadFromEnv(func(key string) string {
		return ""
	})

	if cfg.Port != config.DefaultPort {
		t.Errorf("expected default port %s, got %s", config.DefaultPort, cfg.Port)
	}
	if cfg.AppEnv != config.EnvDevelopment {
		t.Errorf("expected default AppEnv %s, got %s", config.EnvDevelopment, cfg.AppEnv)
	}
	if cfg.IsProduction() {
		t.Errorf("expected IsProduction() false in default dev mode")
	}
	if cfg.RequiresStrictSecrets() {
		t.Errorf("expected RequiresStrictSecrets() false in default dev mode")
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("expected Validate() nil in default dev mode, got %v", err)
	}
	if cfg.DatabaseURL != "" {
		t.Errorf("expected empty DatabaseURL, got %s", cfg.DatabaseURL)
	}
	if cfg.MQTTPort != config.DefaultMQTTPort {
		t.Errorf("expected default MQTT port %s, got %s", config.DefaultMQTTPort, cfg.MQTTPort)
	}
	if cfg.MQTTTLSEnabled {
		t.Errorf("expected MQTTTLSEnabled false by default")
	}
	// MQTT broker URI is intentionally not resolved prematurely during LoadFromEnv
	if cfg.MQTTBrokerURI != "" {
		t.Errorf("expected empty MQTTBrokerURI before resolution, got %s", cfg.MQTTBrokerURI)
	}
	resolvedURI, err := cfg.ResolveMQTTBrokerURI()
	if err != nil {
		t.Fatalf("unexpected error resolving default broker URI: %v", err)
	}
	if resolvedURI != "tcp://127.0.0.1:1883" {
		t.Errorf("expected resolved broker URI tcp://127.0.0.1:1883, got %s", resolvedURI)
	}
	if cfg.MQTTBrokerURI != "tcp://127.0.0.1:1883" {
		t.Errorf("expected cached broker URI tcp://127.0.0.1:1883, got %s", cfg.MQTTBrokerURI)
	}
	if cfg.JWTSecretKey != config.DefaultJWTSecret {
		t.Errorf("expected default JWT secret, got %s", cfg.JWTSecretKey)
	}
	expectedMasterKey := sha256.Sum256([]byte(config.DefaultJWTSecret + ":provision:master:key"))
	if cfg.DeviceProvisionMasterKey != expectedMasterKey {
		t.Errorf("expected derived master key from default JWT secret")
	}
	if cfg.OfflineThreshold != 5*time.Minute {
		t.Errorf("expected default offline threshold 5m, got %v", cfg.OfflineThreshold)
	}
	if cfg.ReadTimeout != 15*time.Second || cfg.WriteTimeout != 15*time.Second || cfg.IdleTimeout != 60*time.Second || cfg.ShutdownTimeout != 5*time.Second {
		t.Errorf("unexpected timeouts: %+v", cfg)
	}
}

func TestLoad_NoUnconditionalDNS(t *testing.T) {
	dnsCalled := false
	dnsLookup := func(host string) ([]string, error) {
		dnsCalled = true
		return []string{"192.168.1.100"}, nil
	}

	// LoadFromEnv must NOT invoke DNS lookup, even if MQTT_HOST is "mqtt-dev"
	cfg := config.LoadFromEnv(func(key string) string {
		if key == "MQTT_HOST" {
			return "mqtt-dev"
		}
		return ""
	}, dnsLookup)

	if dnsCalled {
		t.Fatal("dnsLookup MUST NOT be invoked unconditionally during config.LoadFromEnv")
	}
	if cfg.MQTTBrokerURI != "" {
		t.Errorf("expected empty MQTTBrokerURI before resolution, got %s", cfg.MQTTBrokerURI)
	}

	// DNS lookup is invoked only upon explicit resolution
	uri, err := cfg.ResolveMQTTBrokerURI(dnsLookup)
	if err != nil {
		t.Fatalf("unexpected error resolving mqtt-dev: %v", err)
	}
	if !dnsCalled {
		t.Fatal("dnsLookup MUST be invoked when ResolveMQTTBrokerURI is called")
	}
	if uri != "tcp://192.168.1.100:1883" && uri != "tcp://mqtt-dev:1883" {
		t.Errorf("unexpected resolved URI: %s", uri)
	}
}

func TestLoad_CustomEnv(t *testing.T) {
	env := map[string]string{
		"PORT":                        "9090",
		"DATABASE_URL":                "postgres://user:pass@localhost:5432/testdb",
		"MQTT_HOST":                   "10.0.0.5",
		"MQTT_PORT":                   "1884",
		"JWT_SECRET_KEY":              "my-custom-super-secure-jwt-secret-key-32-bytes!",
		"DEVICE_PROVISION_MASTER_KEY": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
	}

	cfg := config.LoadFromEnv(func(key string) string {
		return env[key]
	})

	if cfg.Port != "9090" {
		t.Errorf("expected port 9090, got %s", cfg.Port)
	}
	if cfg.DatabaseURL != "postgres://user:pass@localhost:5432/testdb" {
		t.Errorf("expected custom database URL, got %s", cfg.DatabaseURL)
	}
	uri, err := cfg.ResolveMQTTBrokerURI()
	if err != nil {
		t.Fatalf("unexpected error resolving broker URI: %v", err)
	}
	if uri != "tcp://10.0.0.5:1884" {
		t.Errorf("expected broker URI tcp://10.0.0.5:1884, got %s", uri)
	}
	if cfg.JWTSecretKey != "my-custom-super-secure-jwt-secret-key-32-bytes!" {
		t.Errorf("expected custom JWT secret, got %s", cfg.JWTSecretKey)
	}
	expectedKey, _ := hex.DecodeString(env["DEVICE_PROVISION_MASTER_KEY"])
	var expectedArr [32]byte
	copy(expectedArr[:], expectedKey)
	if cfg.DeviceProvisionMasterKey != expectedArr {
		t.Errorf("expected decoded master key, got %x", cfg.DeviceProvisionMasterKey)
	}
}

func TestLoad_RawProvisionMasterKey(t *testing.T) {
	rawKey := "12345678901234567890123456789012" // 32 characters
	cfg := config.LoadFromEnv(func(key string) string {
		if key == "DEVICE_PROVISION_MASTER_KEY" {
			return rawKey
		}
		return ""
	})

	var expectedArr [32]byte
	copy(expectedArr[:], []byte(rawKey))
	if cfg.DeviceProvisionMasterKey != expectedArr {
		t.Errorf("expected raw copied master key, got %x", cfg.DeviceProvisionMasterKey)
	}
}

func TestLoad_MQTTDevResolution(t *testing.T) {
	tests := []struct {
		name         string
		dnsMap       map[string]bool
		expectedHost string
		expectErr    bool
	}{
		{
			name:         "mqtt-dev resolves successfully",
			dnsMap:       map[string]bool{"mqtt-dev": true},
			expectedHost: "mqtt-dev",
		},
		{
			name:         "mqtt-dev fails, deploy-mqtt-dev-1 resolves",
			dnsMap:       map[string]bool{"mqtt-dev": false, "deploy-mqtt-dev-1": true},
			expectedHost: "deploy-mqtt-dev-1",
		},
		{
			name:      "mqtt-dev and deploy-mqtt-dev-1 fail, returns explicit error (no LAN IP fallback)",
			dnsMap:    map[string]bool{"mqtt-dev": false, "deploy-mqtt-dev-1": false},
			expectErr: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			lookup := func(host string) ([]string, error) {
				if tc.dnsMap[host] {
					return []string{"192.168.1.1"}, nil
				}
				return nil, errors.New("lookup failed")
			}
			cfg := config.LoadFromEnv(func(key string) string {
				if key == "MQTT_HOST" {
					return "mqtt-dev"
				}
				return ""
			}, lookup)

			resolvedURI, err := cfg.ResolveMQTTBrokerURI(lookup)
			if tc.expectErr {
				if err == nil {
					t.Fatalf("expected error for unresolved mqtt-dev host, got URI %s", resolvedURI)
				}
				if !errors.Is(err, config.ErrUnresolvedMQTTHost) {
					t.Errorf("expected ErrUnresolvedMQTTHost, got %v", err)
				}
				if strings.Contains(resolvedURI, "192.168.88.113") || strings.Contains(err.Error(), "192.168.88.113") {
					t.Errorf("hardcoded LAN IP 192.168.88.113 must not appear in URI or error")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			expectedURI := "tcp://" + tc.expectedHost + ":1883"
			if resolvedURI != expectedURI {
				t.Errorf("expected broker URI %s, got %s", expectedURI, resolvedURI)
			}
		})
	}
}

func TestLoad_LocalhostMQTT(t *testing.T) {
	cfg := config.LoadFromEnv(func(key string) string {
		if key == "MQTT_HOST" {
			return "localhost"
		}
		return ""
	})
	uri, err := cfg.ResolveMQTTBrokerURI()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if uri != "tcp://127.0.0.1:1883" {
		t.Errorf("expected localhost to resolve to 127.0.0.1, got %s", uri)
	}
}

func TestLoad_TLSConfigParsingAndURIScheme(t *testing.T) {
	env := map[string]string{
		"MQTT_HOST":            "mqtt-tls",
		"MQTT_TLS_ENABLED":     "true",
		"MQTT_TLS_CA_FILE":     "/run/secrets/mqtt/ca.crt",
		"MQTT_TLS_CERT_FILE":   "/run/secrets/mqtt/backend.crt",
		"MQTT_TLS_KEY_FILE":    "/run/secrets/mqtt/backend.key",
		"MQTT_TLS_SERVER_NAME": "mqtt-tls.internal",
		"MQTT_USERNAME":        "backend",
		"MQTT_PASSWORD":        "REPLACE_WITH_TEST_CREDENTIAL",
	}

	cfg := config.LoadFromEnv(func(key string) string {
		return env[key]
	})

	if !cfg.MQTTTLSEnabled {
		t.Fatal("expected MQTTTLSEnabled true")
	}
	if cfg.MQTTPort != config.DefaultMQTTTLSPort {
		t.Errorf("expected default TLS port %s, got %s", config.DefaultMQTTTLSPort, cfg.MQTTPort)
	}
	if cfg.MQTTTLSCAFile != "/run/secrets/mqtt/ca.crt" ||
		cfg.MQTTTLSCertFile != "/run/secrets/mqtt/backend.crt" ||
		cfg.MQTTTLSKeyFile != "/run/secrets/mqtt/backend.key" ||
		cfg.MQTTTLSServerName != "mqtt-tls.internal" ||
		cfg.MQTTUsername != "backend" ||
		cfg.MQTTPassword != "REPLACE_WITH_TEST_CREDENTIAL" {
		t.Errorf("unexpected parsed TLS/auth config fields: %s", cfg.String())
	}

	uri, err := cfg.ResolveMQTTBrokerURI()
	if err != nil {
		t.Fatalf("unexpected error resolving TLS URI: %v", err)
	}
	if uri != "tls://mqtt-tls:8883" {
		t.Errorf("expected tls://mqtt-tls:8883, got %s", uri)
	}

	// Verify localhost preserves hostname when TLS is enabled for SNI/SAN verification
	localTLSCfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "MQTT_HOST":
			return "localhost"
		case "MQTT_TLS_ENABLED":
			return "true"
		default:
			return ""
		}
	})
	localURI, err := localTLSCfg.ResolveMQTTBrokerURI()
	if err != nil {
		t.Fatalf("unexpected error resolving localhost TLS URI: %v", err)
	}
	if localURI != "tls://localhost:8883" {
		t.Errorf("expected tls://localhost:8883, got %s", localURI)
	}
}

func TestLoad_InvalidTLSEnabled_FailsClosed(t *testing.T) {
	cfg := config.LoadFromEnv(func(key string) string {
		if key == "MQTT_TLS_ENABLED" {
			return "not-a-bool"
		}
		return ""
	})

	if _, err := cfg.ResolveMQTTBrokerURI(); !errors.Is(err, config.ErrInvalidMQTTConfig) {
		t.Errorf("expected ErrInvalidMQTTConfig from ResolveMQTTBrokerURI, got %v", err)
	}
	if _, err := cfg.BuildMQTTTLSConfig(); !errors.Is(err, config.ErrInvalidMQTTConfig) {
		t.Errorf("expected ErrInvalidMQTTConfig from BuildMQTTTLSConfig, got %v", err)
	}
}

func TestResolveMQTTBrokerURI_InvalidPortAndHost(t *testing.T) {
	for _, tc := range []struct {
		name string
		host string
		port string
	}{
		{name: "non-numeric port", host: "mqtt-tls", port: "abc"},
		{name: "zero port", host: "mqtt-tls", port: "0"},
		{name: "port overflow", host: "mqtt-tls", port: "70000"},
		{name: "host with credentials", host: "user:pass@mqtt-tls", port: "8883"},
		{name: "host with space", host: "mqtt tls", port: "8883"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := config.ResolveMQTTBrokerURIWithScheme(tc.host, tc.port, true); !errors.Is(err, config.ErrInvalidMQTTConfig) {
				t.Errorf("expected ErrInvalidMQTTConfig for (%q, %q), got %v", tc.host, tc.port, err)
			}
		})
	}
}

func writeTestCertPair(t *testing.T, dir, prefix string, isCA bool, signerCert *x509.Certificate, signerKey *ecdsa.PrivateKey) (string, string, *x509.Certificate, *ecdsa.PrivateKey) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	serial, err := rand.Int(rand.Reader, big.NewInt(1<<62))
	if err != nil {
		t.Fatalf("serial: %v", err)
	}
	tmpl := &x509.Certificate{
		SerialNumber:          serial,
		Subject:               pkix.Name{CommonName: prefix},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		BasicConstraintsValid: true,
	}
	if isCA {
		tmpl.IsCA = true
		tmpl.KeyUsage |= x509.KeyUsageCertSign
	} else {
		tmpl.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}
	}
	parent := tmpl
	signingKey := key
	if signerCert != nil && signerKey != nil {
		parent = signerCert
		signingKey = signerKey
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, parent, &key.PublicKey, signingKey)
	if err != nil {
		t.Fatalf("create cert: %v", err)
	}
	parsedCert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatalf("parse cert: %v", err)
	}
	certPath := filepath.Join(dir, prefix+".crt")
	keyPath := filepath.Join(dir, prefix+".key")
	if err := os.WriteFile(certPath, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0o600); err != nil {
		t.Fatalf("write cert: %v", err)
	}
	keyDER, err := x509.MarshalECPrivateKey(key)
	if err != nil {
		t.Fatalf("marshal key: %v", err)
	}
	if err := os.WriteFile(keyPath, pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyDER}), 0o600); err != nil {
		t.Fatalf("write key: %v", err)
	}
	return certPath, keyPath, parsedCert, key
}

func TestBuildMQTTTLSConfig_ValidAndFailureModes(t *testing.T) {
	dir := t.TempDir()
	caCertPath, _, caCert, caKey := writeTestCertPair(t, dir, "ca", true, nil, nil)
	clientCertPath, clientKeyPath, _, _ := writeTestCertPair(t, dir, "backend", false, caCert, caKey)
	_, otherKeyPath, _, _ := writeTestCertPair(t, dir, "other", false, caCert, caKey)

	invalidPEMPath := filepath.Join(dir, "invalid.pem")
	if err := os.WriteFile(invalidPEMPath, []byte("not-a-pem"), 0o600); err != nil {
		t.Fatalf("write invalid pem: %v", err)
	}

	t.Run("TLS disabled returns nil without reading files", func(t *testing.T) {
		cfg := &config.Config{MQTTTLSEnabled: false, MQTTTLSCAFile: "/nonexistent/ca.crt"}
		tlsCfg, err := cfg.BuildMQTTTLSConfig()
		if err != nil || tlsCfg != nil {
			t.Fatalf("expected (nil, nil), got (%v, %v)", tlsCfg, err)
		}
	})

	t.Run("Valid mTLS config succeeds with TLS 1.2+ and verified CA", func(t *testing.T) {
		cfg := &config.Config{
			MQTTTLSEnabled:    true,
			MQTTTLSCAFile:     caCertPath,
			MQTTTLSCertFile:   clientCertPath,
			MQTTTLSKeyFile:    clientKeyPath,
			MQTTTLSServerName: "mqtt-tls",
		}
		tlsCfg, err := cfg.BuildMQTTTLSConfig()
		if err != nil {
			t.Fatalf("expected valid mTLS config, got error: %v", err)
		}
		if tlsCfg == nil || tlsCfg.RootCAs == nil || len(tlsCfg.Certificates) != 1 {
			t.Fatalf("expected RootCAs and 1 client certificate, got %+v", tlsCfg)
		}
		if tlsCfg.MinVersion < tls.VersionTLS12 {
			t.Errorf("expected MinVersion >= TLS 1.2, got %d", tlsCfg.MinVersion)
		}
		if tlsCfg.InsecureSkipVerify {
			t.Errorf("InsecureSkipVerify MUST be false")
		}
		if tlsCfg.ServerName != "mqtt-tls" {
			t.Errorf("expected ServerName mqtt-tls, got %s", tlsCfg.ServerName)
		}
	})

	t.Run("Valid TLS with username/password and no client cert succeeds", func(t *testing.T) {
		cfg := &config.Config{
			MQTTTLSEnabled: true,
			MQTTTLSCAFile:  caCertPath,
			MQTTUsername:   "backend",
			MQTTPassword:   "test-password-value",
		}
		tlsCfg, err := cfg.BuildMQTTTLSConfig()
		if err != nil {
			t.Fatalf("expected valid TLS config, got error: %v", err)
		}
		if tlsCfg == nil || tlsCfg.RootCAs == nil || len(tlsCfg.Certificates) != 0 {
			t.Fatalf("expected RootCAs without client certs, got %+v", tlsCfg)
		}
	})

	failureCases := []struct {
		name string
		cfg  config.Config
	}{
		{
			name: "missing CA file path",
			cfg:  config.Config{MQTTTLSEnabled: true},
		},
		{
			name: "nonexistent CA file",
			cfg:  config.Config{MQTTTLSEnabled: true, MQTTTLSCAFile: filepath.Join(dir, "missing-ca.crt")},
		},
		{
			name: "invalid PEM in CA file",
			cfg:  config.Config{MQTTTLSEnabled: true, MQTTTLSCAFile: invalidPEMPath},
		},
		{
			name: "client cert without key",
			cfg:  config.Config{MQTTTLSEnabled: true, MQTTTLSCAFile: caCertPath, MQTTTLSCertFile: clientCertPath},
		},
		{
			name: "client key without cert",
			cfg:  config.Config{MQTTTLSEnabled: true, MQTTTLSCAFile: caCertPath, MQTTTLSKeyFile: clientKeyPath},
		},
		{
			name: "missing client cert file",
			cfg:  config.Config{MQTTTLSEnabled: true, MQTTTLSCAFile: caCertPath, MQTTTLSCertFile: filepath.Join(dir, "missing.crt"), MQTTTLSKeyFile: clientKeyPath},
		},
		{
			name: "missing client key file",
			cfg:  config.Config{MQTTTLSEnabled: true, MQTTTLSCAFile: caCertPath, MQTTTLSCertFile: clientCertPath, MQTTTLSKeyFile: filepath.Join(dir, "missing.key")},
		},
		{
			name: "mismatched client cert and key",
			cfg:  config.Config{MQTTTLSEnabled: true, MQTTTLSCAFile: caCertPath, MQTTTLSCertFile: clientCertPath, MQTTTLSKeyFile: otherKeyPath},
		},
		{
			name: "password without username",
			cfg:  config.Config{MQTTTLSEnabled: true, MQTTTLSCAFile: caCertPath, MQTTPassword: "secret"},
		},
	}

	for _, tc := range failureCases {
		t.Run(tc.name, func(t *testing.T) {
			tlsCfg, err := tc.cfg.BuildMQTTTLSConfig()
			if !errors.Is(err, config.ErrInvalidMQTTConfig) {
				t.Errorf("expected ErrInvalidMQTTConfig, got (%v, %v)", tlsCfg, err)
			}
		})
	}
}

func TestConfig_StringRedaction(t *testing.T) {
	secret := "secret-jwt-key-minimum-32-characters!!"
	cfg := config.LoadFromEnv(func(key string) string {
		if key == "JWT_SECRET_KEY" {
			return secret
		}
		return ""
	})

	str := cfg.String()
	if strings.Contains(str, secret) {
		t.Errorf("Config.String() leaked JWT secret key: %s", str)
	}
}

func TestConfig_StringRedaction_Credentials(t *testing.T) {
	mqttPass := "super-secret-mqtt-pass-98765"
	cfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "DATABASE_URL":
			return "postgres://dbuser:supersecretdbpass@127.0.0.1:5432/proddb"
		case "MQTT_HOST":
			return "mqttuser:supersecretmqttpass@10.0.0.1"
		case "MQTT_PORT":
			return "1883"
		case "MQTT_USERNAME":
			return "backend"
		case "MQTT_PASSWORD":
			return mqttPass
		default:
			return ""
		}
	})

	// Before URI resolution
	strBefore := cfg.String()
	if strings.Contains(strBefore, "supersecretdbpass") {
		t.Errorf("Config.String() leaked database password: %s", strBefore)
	}
	if strings.Contains(strBefore, "supersecretmqttpass") {
		t.Errorf("Config.String() leaked MQTT host password: %s", strBefore)
	}
	if strings.Contains(strBefore, mqttPass) {
		t.Errorf("Config.String() leaked MQTTPassword: %s", strBefore)
	}

	// Manually inject a credentialed broker URI to test URI redaction
	cfg.MQTTBrokerURI = "tcp://brokeruser:secretbrokerpass@10.0.0.1:1883"
	strAfter := cfg.String()
	if strings.Contains(strAfter, "secretbrokerpass") {
		t.Errorf("Config.String() leaked MQTT broker URI password: %s", strAfter)
	}
	if !strings.Contains(strAfter, "tcp://brokeruser:xxxxx@10.0.0.1:1883") {
		t.Errorf("expected redacted URI with xxxxx, got %s", strAfter)
	}
}

func TestLoad_MQTTBrokerURI_DoesNotOverrideHostPort(t *testing.T) {
	env := map[string]string{
		"MQTT_BROKER_URI": "tcp://unauthorized-override:9999",
		"MQTT_HOST":       "legitimate-broker",
		"MQTT_PORT":       "1883",
	}

	cfg := config.LoadFromEnv(func(key string) string {
		return env[key]
	})

	// Initial cached broker URI MUST be empty; LoadFromEnv must NOT read MQTT_BROKER_URI
	if cfg.MQTTBrokerURI != "" {
		t.Errorf("expected empty MQTTBrokerURI before resolution, got %s", cfg.MQTTBrokerURI)
	}

	uri, err := cfg.ResolveMQTTBrokerURI()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if uri != "tcp://legitimate-broker:1883" {
		t.Errorf("expected broker URI tcp://legitimate-broker:1883 derived from host/port, got %s", uri)
	}
	if strings.Contains(uri, "unauthorized-override") || strings.Contains(uri, "9999") {
		t.Errorf("unauthorized MQTT_BROKER_URI overrode host/port: %s", uri)
	}
}

func TestLoad_MQTTBrokerURI_IgnoredWhenHostEmpty(t *testing.T) {
	env := map[string]string{
		"MQTT_BROKER_URI": "tcp://unauthorized-override:9999",
	}

	cfg := config.LoadFromEnv(func(key string) string {
		return env[key]
	})

	uri, err := cfg.ResolveMQTTBrokerURI()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if uri != "tcp://127.0.0.1:1883" {
		t.Errorf("expected default tcp://127.0.0.1:1883, got %s", uri)
	}
	if strings.Contains(uri, "unauthorized-override") {
		t.Errorf("unauthorized MQTT_BROKER_URI leaked into resolution: %s", uri)
	}
}

func TestLoad_ProductionFailFast_SecretsValidation(t *testing.T) {
	validJWT := "prod-super-secure-jwt-secret-key-at-least-32-bytes!"
	validMasterHex := "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

	tests := []struct {
		name           string
		env            map[string]string
		wantErrSubstr  string
		notLeakedValue string
	}{
		{
			name: "missing both secrets in production",
			env: map[string]string{
				"APP_ENV": "production",
			},
			wantErrSubstr: "JWT_SECRET_KEY is required in production",
		},
		{
			name: "short JWT_SECRET_KEY in production",
			env: map[string]string{
				"APP_ENV":                     "production",
				"JWT_SECRET_KEY":              "too-short-secret-key",
				"DEVICE_PROVISION_MASTER_KEY": validMasterHex,
			},
			wantErrSubstr:  "JWT_SECRET_KEY must be at least 32 bytes in production",
			notLeakedValue: "too-short-secret-key",
		},
		{
			name: "default JWT_SECRET_KEY rejected in production",
			env: map[string]string{
				"APP_ENV":                     "production",
				"JWT_SECRET_KEY":              config.DefaultJWTSecret,
				"DEVICE_PROVISION_MASTER_KEY": validMasterHex,
			},
			wantErrSubstr:  "JWT_SECRET_KEY must not use default or placeholder value in production",
			notLeakedValue: config.DefaultJWTSecret,
		},
		{
			name: "legacy compose dev JWT literal rejected in production",
			env: map[string]string{
				"APP_ENV":                     "production",
				"JWT_SECRET_KEY":              "default-dev-jwt-secret-key-min-32-bytes-secure!!",
				"DEVICE_PROVISION_MASTER_KEY": validMasterHex,
			},
			wantErrSubstr:  "JWT_SECRET_KEY must not use default or placeholder value in production",
			notLeakedValue: "default-dev-jwt-secret-key-min-32-bytes-secure!!",
		},
		{
			name: "template placeholder JWT_SECRET_KEY rejected in production",
			env: map[string]string{
				"APP_ENV":                     "production",
				"JWT_SECRET_KEY":              "REPLACE_WITH_STRONG_DEV_JWT_SECRET_KEY_MIN_32_BYTES",
				"DEVICE_PROVISION_MASTER_KEY": validMasterHex,
			},
			wantErrSubstr:  "JWT_SECRET_KEY must not use default or placeholder value in production",
			notLeakedValue: "REPLACE_WITH_STRONG_DEV_JWT_SECRET_KEY_MIN_32_BYTES",
		},
		{
			name: "missing DEVICE_PROVISION_MASTER_KEY in production",
			env: map[string]string{
				"APP_ENV":        "production",
				"JWT_SECRET_KEY": validJWT,
			},
			wantErrSubstr: "DEVICE_PROVISION_MASTER_KEY is required in production",
		},
		{
			name: "short DEVICE_PROVISION_MASTER_KEY in production",
			env: map[string]string{
				"APP_ENV":                     "production",
				"JWT_SECRET_KEY":              validJWT,
				"DEVICE_PROVISION_MASTER_KEY": "short-master-key",
			},
			wantErrSubstr:  "DEVICE_PROVISION_MASTER_KEY must be 64 hex characters or at least 32 bytes",
			notLeakedValue: "short-master-key",
		},
		{
			name: "invalid 64-char non-hex DEVICE_PROVISION_MASTER_KEY in production",
			env: map[string]string{
				"APP_ENV":                     "production",
				"JWT_SECRET_KEY":              validJWT,
				"DEVICE_PROVISION_MASTER_KEY": strings.Repeat("z", 64),
			},
			wantErrSubstr:  "DEVICE_PROVISION_MASTER_KEY of length 64 must be valid hex",
			notLeakedValue: strings.Repeat("z", 64),
		},
		{
			name: "all-zero DEVICE_PROVISION_MASTER_KEY rejected in production",
			env: map[string]string{
				"APP_ENV":                     "production",
				"JWT_SECRET_KEY":              validJWT,
				"DEVICE_PROVISION_MASTER_KEY": strings.Repeat("0", 64),
			},
			wantErrSubstr: "DEVICE_PROVISION_MASTER_KEY must not be all zeros",
		},
		{
			name: "staging mode also enforces strict secrets",
			env: map[string]string{
				"APP_ENV": "staging",
			},
			wantErrSubstr: "JWT_SECRET_KEY is required in production",
		},
		{
			name: "unknown APP_ENV fails fast instead of falling back to dev",
			env: map[string]string{
				"APP_ENV": "producton",
			},
			wantErrSubstr: "invalid APP_ENV",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			cfg, err := config.LoadFromEnvWithError(func(key string) string {
				return tc.env[key]
			})
			if err == nil {
				t.Fatalf("expected error for %s, got nil (cfg=%v)", tc.name, cfg.String())
			}
			if !strings.Contains(err.Error(), tc.wantErrSubstr) {
				t.Errorf("expected error containing %q, got %q", tc.wantErrSubstr, err.Error())
			}
			if tc.notLeakedValue != "" && strings.Contains(err.Error(), tc.notLeakedValue) {
				t.Errorf("error leaked secret material %q: %s", tc.notLeakedValue, err.Error())
			}

			rawCfg := config.LoadFromEnv(func(key string) string {
				return tc.env[key]
			})
			if rawCfg.JWTSecretKey == config.DefaultJWTSecret {
				t.Errorf("strict mode MUST NOT fall back to DefaultJWTSecret")
			}
			if err := rawCfg.Validate(); err == nil {
				t.Errorf("expected rawCfg.Validate() to fail for %s", tc.name)
			}
		})
	}
}

func TestLoad_ProductionValidSecrets(t *testing.T) {
	validJWT := "prod-super-secure-jwt-secret-key-at-least-32-bytes!"
	validMasterHex := "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

	cfg, err := config.LoadFromEnvWithError(func(key string) string {
		switch key {
		case "APP_ENV":
			return "production"
		case "JWT_SECRET_KEY":
			return validJWT
		case "DEVICE_PROVISION_MASTER_KEY":
			return validMasterHex
		default:
			return ""
		}
	})
	if err != nil {
		t.Fatalf("expected valid production config, got error: %v", err)
	}
	if !cfg.IsProduction() || !cfg.RequiresStrictSecrets() {
		t.Errorf("expected IsProduction() and RequiresStrictSecrets() true, got AppEnv=%q", cfg.AppEnv)
	}
	if cfg.JWTSecretKey != validJWT {
		t.Errorf("expected configured JWT secret")
	}
	if strings.Contains(cfg.String(), validJWT) || strings.Contains(cfg.String(), validMasterHex) {
		t.Errorf("Config.String() leaked secret material: %s", cfg.String())
	}
}

func TestConfig_ValidateDirectStructRejectsDerivedMasterKeyInProduction(t *testing.T) {
	jwtSecret := "prod-super-secure-jwt-secret-key-at-least-32-bytes!"
	derived := sha256.Sum256([]byte(jwtSecret + ":provision:master:key"))
	cfg := &config.Config{
		AppEnv:                   config.EnvProduction,
		JWTSecretKey:             jwtSecret,
		DeviceProvisionMasterKey: derived,
	}
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected Validate() to reject derived master key in production")
	}
}

func TestLoad_PostgresSSLMode(t *testing.T) {
	cfg, err := config.LoadFromEnvWithError(func(key string) string {
		switch key {
		case "DATABASE_URL":
			return "postgres://user:secretpass@db.example.com:5432/lora"
		case "POSTGRES_SSLMODE":
			return "verify-full"
		default:
			return ""
		}
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.PostgresSSLMode != "verify-full" {
		t.Errorf("expected PostgresSSLMode verify-full, got %q", cfg.PostgresSSLMode)
	}
	if !strings.Contains(cfg.DatabaseURL, "sslmode=verify-full") {
		t.Errorf("expected sslmode=verify-full in DatabaseURL, got %q", cfg.DatabaseURL)
	}

	// Explicit sslmode in DATABASE_URL is preserved
	cfg2, err := config.LoadFromEnvWithError(func(key string) string {
		switch key {
		case "DATABASE_URL":
			return "postgres://user:secretpass@db.example.com:5432/lora?sslmode=require"
		case "POSTGRES_SSLMODE":
			return "disable"
		default:
			return ""
		}
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(cfg2.DatabaseURL, "sslmode=require") || strings.Contains(cfg2.DatabaseURL, "sslmode=disable") {
		t.Errorf("expected explicit sslmode=require preserved, got %q", cfg2.DatabaseURL)
	}

	// Invalid POSTGRES_SSLMODE fails validation without leaking DATABASE_URL credentials
	_, err = config.LoadFromEnvWithError(func(key string) string {
		switch key {
		case "DATABASE_URL":
			return "postgres://user:supersecretdbpass@db.example.com:5432/lora"
		case "POSTGRES_SSLMODE":
			return "insecure-bogus"
		default:
			return ""
		}
	})
	if err == nil {
		t.Fatal("expected error for invalid POSTGRES_SSLMODE")
	}
	if strings.Contains(err.Error(), "supersecretdbpass") {
		t.Errorf("error leaked database password: %s", err.Error())
	}
}
