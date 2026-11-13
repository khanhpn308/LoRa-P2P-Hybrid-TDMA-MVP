package config_test

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
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
	if cfg.DatabaseURL != "" {
		t.Errorf("expected empty DatabaseURL, got %s", cfg.DatabaseURL)
	}
	if cfg.MQTTPort != config.DefaultMQTTPort {
		t.Errorf("expected default MQTT port %s, got %s", config.DefaultMQTTPort, cfg.MQTTPort)
	}
	// MQTT broker URI is intentionally not resolved prematurely during LoadFromEnv
	if cfg.MQTTBrokerURI != "" {
		t.Errorf("expected empty MQTTBrokerURI before resolution, got %s", cfg.MQTTBrokerURI)
	}
	resolvedURI := cfg.ResolveMQTTBrokerURI()
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
	uri := cfg.ResolveMQTTBrokerURI(dnsLookup)
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
	if uri := cfg.ResolveMQTTBrokerURI(); uri != "tcp://10.0.0.5:1884" {
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
			name:         "mqtt-dev and deploy-mqtt-dev-1 fail, fallback to IP",
			dnsMap:       map[string]bool{"mqtt-dev": false, "deploy-mqtt-dev-1": false},
			expectedHost: "192.168.88.113",
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

			expectedURI := "tcp://" + tc.expectedHost + ":1883"
			resolvedURI := cfg.ResolveMQTTBrokerURI(lookup)
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
	if uri := cfg.ResolveMQTTBrokerURI(); uri != "tcp://127.0.0.1:1883" {
		t.Errorf("expected localhost to resolve to 127.0.0.1, got %s", uri)
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
