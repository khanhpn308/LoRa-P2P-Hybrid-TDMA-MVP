package config

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net"
	"net/url"
	"os"
	"strings"
	"time"
)

const (
	DefaultPort             = "8080"
	DefaultMQTTPort         = "1883"
	DefaultJWTSecret        = "default-mvp-jwt-secret-key-minimum-32-bytes!!"
	DefaultOfflineThreshold = 5 * time.Minute
	DefaultReadTimeout      = 15 * time.Second
	DefaultWriteTimeout     = 15 * time.Second
	DefaultIdleTimeout      = 60 * time.Second
	DefaultShutdownTimeout  = 5 * time.Second
)

// Config encapsulates configuration for the Go backend server.
type Config struct {
	Port                     string
	DatabaseURL              string
	MQTTHost                 string
	MQTTPort                 string
	MQTTBrokerURI            string
	LookupHost               LookupHostFunc
	JWTSecretKey             string
	DeviceProvisionMasterKey [32]byte
	OfflineThreshold         time.Duration
	ReadTimeout              time.Duration
	WriteTimeout             time.Duration
	IdleTimeout              time.Duration
	ShutdownTimeout          time.Duration
}

// redactURI removes password credentials from a URI string.
func redactURI(raw string) string {
	if raw == "" {
		return ""
	}
	u, err := url.Parse(raw)
	if err != nil {
		return "[redacted-uri]"
	}
	return u.Redacted()
}

// sanitizeHost strips potential credentials (user:pass@) if present in a host string.
func sanitizeHost(host string) string {
	if idx := strings.Index(host, "@"); idx != -1 {
		return host[idx+1:]
	}
	return host
}

// String provides a redacted string representation of Config, keeping key material out of logs.
func (c *Config) String() string {
	hasMasterKey := c.DeviceProvisionMasterKey != [32]byte{}
	return fmt.Sprintf(
		"Config{Port:%s, DatabaseURLSet:%t, MQTTHost:%s, MQTTPort:%s, MQTTBrokerURI:%s, JWTSecretKeyLen:%d, MasterKeySet:%t}",
		c.Port,
		c.DatabaseURL != "",
		sanitizeHost(c.MQTTHost),
		c.MQTTPort,
		redactURI(c.MQTTBrokerURI),
		len(c.JWTSecretKey),
		hasMasterKey,
	)
}

// LookupHostFunc matches the signature of net.LookupHost.
type LookupHostFunc func(host string) (addrs []string, err error)

// ResolveMQTTBrokerURI resolves the broker URI for the given host and port with DNS fallback rules.
// DNS lookup for "mqtt-dev" is performed only when this function is called.
func ResolveMQTTBrokerURI(host, port string, lookupHost ...LookupHostFunc) string {
	var dnsLookup LookupHostFunc
	if len(lookupHost) > 0 && lookupHost[0] != nil {
		dnsLookup = lookupHost[0]
	} else {
		dnsLookup = net.LookupHost
	}

	if port == "" {
		port = DefaultMQTTPort
	}

	resolvedHost := host
	if resolvedHost == "" || resolvedHost == "localhost" {
		resolvedHost = "127.0.0.1"
	} else if resolvedHost == "mqtt-dev" {
		if _, err := dnsLookup("mqtt-dev"); err != nil {
			if _, err2 := dnsLookup("deploy-mqtt-dev-1"); err2 == nil {
				resolvedHost = "deploy-mqtt-dev-1"
			} else {
				resolvedHost = "192.168.88.113"
			}
		}
	}
	return fmt.Sprintf("tcp://%s:%s", resolvedHost, port)
}

// ResolveMQTTBrokerURI resolves the broker URI for this Config instance.
// The broker URI is derived exclusively from MQTTHost, MQTTPort, and DNS fallback rules.
// Internal caching of the resolved URI on c.MQTTBrokerURI preserves existing behavior
// and avoids repeated DNS lookups.
func (c *Config) ResolveMQTTBrokerURI(lookupHost ...LookupHostFunc) string {
	if c.MQTTBrokerURI != "" {
		return c.MQTTBrokerURI
	}
	lookup := c.LookupHost
	if len(lookupHost) > 0 && lookupHost[0] != nil {
		lookup = lookupHost[0]
	}
	c.MQTTBrokerURI = ResolveMQTTBrokerURI(c.MQTTHost, c.MQTTPort, lookup)
	return c.MQTTBrokerURI
}

// Load reads backend configuration from OS environment variables.
func Load() *Config {
	return LoadFromEnv(os.Getenv)
}

// LoadFromEnv loads configuration using custom environment accessor.
// Note: MQTT host resolution and DNS lookups are intentionally NOT performed
// during LoadFromEnv to preserve conditional resolution and prevent unconditional DNS I/O.
func LoadFromEnv(getEnv func(string) string, lookupHost ...LookupHostFunc) *Config {
	if getEnv == nil {
		getEnv = os.Getenv
	}

	var dns LookupHostFunc
	if len(lookupHost) > 0 && lookupHost[0] != nil {
		dns = lookupHost[0]
	}

	port := getEnv("PORT")
	if port == "" {
		port = DefaultPort
	}

	dbURL := getEnv("DATABASE_URL")

	mqttHost := getEnv("MQTT_HOST")
	mqttPort := getEnv("MQTT_PORT")
	if mqttPort == "" {
		mqttPort = DefaultMQTTPort
	}

	jwtSecret := getEnv("JWT_SECRET_KEY")
	if len(jwtSecret) < 32 {
		jwtSecret = DefaultJWTSecret
	}

	var masterKey [32]byte
	provisionKeyEnv := getEnv("DEVICE_PROVISION_MASTER_KEY")
	if len(provisionKeyEnv) == 64 {
		decoded, err := hex.DecodeString(provisionKeyEnv)
		if err == nil && len(decoded) == 32 {
			copy(masterKey[:], decoded)
		}
	} else if len(provisionKeyEnv) >= 32 {
		copy(masterKey[:], []byte(provisionKeyEnv[:32]))
	}
	if masterKey == [32]byte{} {
		h := sha256.Sum256([]byte(jwtSecret + ":provision:master:key"))
		copy(masterKey[:], h[:])
	}

	return &Config{
		Port:                     port,
		DatabaseURL:              dbURL,
		MQTTHost:                 mqttHost,
		MQTTPort:                 mqttPort,
		LookupHost:               dns,
		JWTSecretKey:             jwtSecret,
		DeviceProvisionMasterKey: masterKey,
		OfflineThreshold:         DefaultOfflineThreshold,
		ReadTimeout:              DefaultReadTimeout,
		WriteTimeout:             DefaultWriteTimeout,
		IdleTimeout:              DefaultIdleTimeout,
		ShutdownTimeout:          DefaultShutdownTimeout,
	}
}
