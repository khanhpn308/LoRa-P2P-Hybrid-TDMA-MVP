package config

import (
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"errors"
	"fmt"
	"net"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	DefaultPort             = "8080"
	DefaultMQTTPort         = "1883"
	DefaultMQTTTLSPort      = "8883"
	DefaultJWTSecret        = "default-mvp-jwt-secret-key-minimum-32-bytes!!"
	DefaultOfflineThreshold = 5 * time.Minute
	DefaultReadTimeout      = 15 * time.Second
	DefaultWriteTimeout     = 15 * time.Second
	DefaultIdleTimeout      = 60 * time.Second
	DefaultShutdownTimeout  = 5 * time.Second
)

var (
	// ErrUnresolvedMQTTHost is returned when a broker hostname cannot be resolved via DNS.
	ErrUnresolvedMQTTHost = errors.New("unresolved MQTT broker host")
	// ErrInvalidMQTTConfig is returned when MQTT TLS or authentication configuration is invalid or incomplete.
	ErrInvalidMQTTConfig = errors.New("invalid MQTT configuration")
)

// Config encapsulates configuration for the Go backend server.
type Config struct {
	Port                     string
	DatabaseURL              string
	MQTTHost                 string
	MQTTPort                 string
	MQTTBrokerURI            string
	MQTTTLSEnabled           bool
	MQTTTLSCAFile            string
	MQTTTLSCertFile          string
	MQTTTLSKeyFile           string
	MQTTTLSServerName        string
	MQTTUsername             string
	MQTTPassword             string
	mqttTLSConfigErr         error
	LookupHost               LookupHostFunc
	JWTSecretKey             string
	DeviceProvisionMasterKey [32]byte
	OfflineThreshold         time.Duration
	ReadTimeout              time.Duration
	WriteTimeout             time.Duration
	IdleTimeout              time.Duration
	ShutdownTimeout          time.Duration
}

// RedactURI removes password credentials from a URI string for safe logging.
func RedactURI(raw string) string {
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

// String provides a redacted string representation of Config, keeping key material and credentials out of logs.
func (c *Config) String() string {
	hasMasterKey := c.DeviceProvisionMasterKey != [32]byte{}
	return fmt.Sprintf(
		"Config{Port:%s, DatabaseURLSet:%t, MQTTHost:%s, MQTTPort:%s, MQTTBrokerURI:%s, MQTTTLSEnabled:%t, MQTTTLSCAFileSet:%t, MQTTTLSCertSet:%t, MQTTTLSKeySet:%t, MQTTUsernameSet:%t, MQTTPasswordSet:%t, JWTSecretKeyLen:%d, MasterKeySet:%t}",
		c.Port,
		c.DatabaseURL != "",
		sanitizeHost(c.MQTTHost),
		c.MQTTPort,
		RedactURI(c.MQTTBrokerURI),
		c.MQTTTLSEnabled,
		c.MQTTTLSCAFile != "",
		c.MQTTTLSCertFile != "",
		c.MQTTTLSKeyFile != "",
		c.MQTTUsername != "",
		c.MQTTPassword != "",
		len(c.JWTSecretKey),
		hasMasterKey,
	)
}

// LookupHostFunc matches the signature of net.LookupHost.
type LookupHostFunc func(host string) (addrs []string, err error)

// ResolveMQTTBrokerURIWithScheme resolves the broker URI for the given host, port, and TLS setting.
// Fails explicitly if the broker host cannot be resolved rather than falling back to a hardcoded IP.
func ResolveMQTTBrokerURIWithScheme(host, port string, tlsEnabled bool, lookupHost ...LookupHostFunc) (string, error) {
	var dnsLookup LookupHostFunc
	if len(lookupHost) > 0 && lookupHost[0] != nil {
		dnsLookup = lookupHost[0]
	} else {
		dnsLookup = net.LookupHost
	}

	scheme := "tcp"
	defaultPort := DefaultMQTTPort
	if tlsEnabled {
		scheme = "tls"
		defaultPort = DefaultMQTTTLSPort
	}

	port = strings.TrimSpace(port)
	if port == "" {
		port = defaultPort
	} else {
		portNum, err := strconv.Atoi(port)
		if err != nil || portNum < 1 || portNum > 65535 {
			return "", fmt.Errorf("%w: invalid MQTT port %q", ErrInvalidMQTTConfig, port)
		}
	}

	resolvedHost := strings.TrimSpace(host)
	if strings.ContainsAny(resolvedHost, " \t\r\n/@") {
		return "", fmt.Errorf("%w: invalid MQTT host", ErrInvalidMQTTConfig)
	}

	switch resolvedHost {
	case "":
		resolvedHost = "127.0.0.1"
	case "localhost":
		if tlsEnabled {
			resolvedHost = "localhost"
		} else {
			resolvedHost = "127.0.0.1"
		}
	case "mqtt-dev":
		if _, err := dnsLookup("mqtt-dev"); err != nil {
			if _, err2 := dnsLookup("deploy-mqtt-dev-1"); err2 == nil {
				resolvedHost = "deploy-mqtt-dev-1"
			} else {
				return "", fmt.Errorf("%w: %q (and fallback %q): %v", ErrUnresolvedMQTTHost, "mqtt-dev", "deploy-mqtt-dev-1", err2)
			}
		}
	}

	return fmt.Sprintf("%s://%s:%s", scheme, resolvedHost, port), nil
}

// ResolveMQTTBrokerURI resolves a plaintext tcp:// broker URI for the given host and port with DNS rules.
// Fails explicitly if the broker host cannot be resolved.
func ResolveMQTTBrokerURI(host, port string, lookupHost ...LookupHostFunc) (string, error) {
	return ResolveMQTTBrokerURIWithScheme(host, port, false, lookupHost...)
}

// ResolveMQTTBrokerURI resolves the broker URI for this Config instance.
// The broker URI is derived exclusively from MQTTHost, MQTTPort, MQTTTLSEnabled, and DNS rules.
// Internal caching of the resolved URI on c.MQTTBrokerURI preserves existing behavior
// and avoids repeated DNS lookups.
func (c *Config) ResolveMQTTBrokerURI(lookupHost ...LookupHostFunc) (string, error) {
	if c.mqttTLSConfigErr != nil {
		return "", c.mqttTLSConfigErr
	}
	if c.MQTTBrokerURI != "" {
		return c.MQTTBrokerURI, nil
	}
	lookup := c.LookupHost
	if len(lookupHost) > 0 && lookupHost[0] != nil {
		lookup = lookupHost[0]
	}
	uri, err := ResolveMQTTBrokerURIWithScheme(c.MQTTHost, c.MQTTPort, c.MQTTTLSEnabled, lookup)
	if err != nil {
		return "", err
	}
	c.MQTTBrokerURI = uri
	return c.MQTTBrokerURI, nil
}

// BuildMQTTTLSConfig validates MQTT TLS/auth settings and returns a *tls.Config when TLS is enabled.
// Fails closed if TLS is enabled and CA or configured client certificate/key files are missing, unreadable, or invalid.
func (c *Config) BuildMQTTTLSConfig() (*tls.Config, error) {
	if c.mqttTLSConfigErr != nil {
		return nil, c.mqttTLSConfigErr
	}
	if c.MQTTPassword != "" && c.MQTTUsername == "" {
		return nil, fmt.Errorf("%w: MQTT_PASSWORD requires MQTT_USERNAME", ErrInvalidMQTTConfig)
	}
	if !c.MQTTTLSEnabled {
		return nil, nil
	}

	caFile := strings.TrimSpace(c.MQTTTLSCAFile)
	if caFile == "" {
		return nil, fmt.Errorf("%w: MQTT_TLS_CA_FILE is required when MQTT TLS is enabled", ErrInvalidMQTTConfig)
	}
	caPEM, err := os.ReadFile(caFile)
	if err != nil {
		return nil, fmt.Errorf("%w: failed to read MQTT CA cert file %q: %v", ErrInvalidMQTTConfig, caFile, err)
	}
	caPool := x509.NewCertPool()
	if !caPool.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("%w: MQTT CA cert file %q contains no valid PEM certificates", ErrInvalidMQTTConfig, caFile)
	}

	tlsCfg := &tls.Config{
		MinVersion:         tls.VersionTLS12,
		RootCAs:            caPool,
		InsecureSkipVerify: false,
		ServerName:         strings.TrimSpace(c.MQTTTLSServerName),
	}

	certFile := strings.TrimSpace(c.MQTTTLSCertFile)
	keyFile := strings.TrimSpace(c.MQTTTLSKeyFile)
	if (certFile != "") != (keyFile != "") {
		return nil, fmt.Errorf("%w: MQTT_TLS_CERT_FILE and MQTT_TLS_KEY_FILE must both be set for mTLS", ErrInvalidMQTTConfig)
	}
	if certFile != "" && keyFile != "" {
		if _, err := os.Stat(certFile); err != nil {
			return nil, fmt.Errorf("%w: MQTT client cert file %q is not accessible: %v", ErrInvalidMQTTConfig, certFile, err)
		}
		if _, err := os.Stat(keyFile); err != nil {
			return nil, fmt.Errorf("%w: MQTT client key file %q is not accessible: %v", ErrInvalidMQTTConfig, keyFile, err)
		}
		cert, err := tls.LoadX509KeyPair(certFile, keyFile)
		if err != nil {
			return nil, fmt.Errorf("%w: failed to load MQTT client certificate/key pair: %v", ErrInvalidMQTTConfig, err)
		}
		tlsCfg.Certificates = []tls.Certificate{cert}
	}

	return tlsCfg, nil
}

// Load reads backend configuration from OS environment variables.
func Load() *Config {
	return LoadFromEnv(os.Getenv)
}

// LoadFromEnv loads configuration using custom environment accessor.
// Note: MQTT host resolution, DNS lookups, and TLS file reads are intentionally NOT performed
// during LoadFromEnv to preserve conditional resolution and prevent unconditional I/O.
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

	var tlsEnabled bool
	var mqttTLSConfigErr error
	rawTLSEnabled := strings.TrimSpace(getEnv("MQTT_TLS_ENABLED"))
	if rawTLSEnabled != "" {
		parsed, err := strconv.ParseBool(rawTLSEnabled)
		if err != nil {
			mqttTLSConfigErr = fmt.Errorf("%w: invalid MQTT_TLS_ENABLED %q: %v", ErrInvalidMQTTConfig, rawTLSEnabled, err)
		} else {
			tlsEnabled = parsed
		}
	}

	mqttHost := getEnv("MQTT_HOST")
	mqttPort := strings.TrimSpace(getEnv("MQTT_PORT"))
	if mqttPort == "" {
		if tlsEnabled {
			mqttPort = DefaultMQTTTLSPort
		} else {
			mqttPort = DefaultMQTTPort
		}
	}

	mqttTLSCAFile := strings.TrimSpace(getEnv("MQTT_TLS_CA_FILE"))
	mqttTLSCertFile := strings.TrimSpace(getEnv("MQTT_TLS_CERT_FILE"))
	mqttTLSKeyFile := strings.TrimSpace(getEnv("MQTT_TLS_KEY_FILE"))
	mqttTLSServerName := strings.TrimSpace(getEnv("MQTT_TLS_SERVER_NAME"))
	mqttUsername := getEnv("MQTT_USERNAME")
	mqttPassword := getEnv("MQTT_PASSWORD")

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
		MQTTTLSEnabled:           tlsEnabled,
		MQTTTLSCAFile:            mqttTLSCAFile,
		MQTTTLSCertFile:          mqttTLSCertFile,
		MQTTTLSKeyFile:           mqttTLSKeyFile,
		MQTTTLSServerName:        mqttTLSServerName,
		MQTTUsername:             mqttUsername,
		MQTTPassword:             mqttPassword,
		mqttTLSConfigErr:         mqttTLSConfigErr,
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
