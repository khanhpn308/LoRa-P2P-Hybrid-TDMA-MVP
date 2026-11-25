package config

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
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
	DefaultAppEnv           = EnvDevelopment
	EnvDevelopment          = "development"
	EnvStaging              = "staging"
	EnvProduction           = "production"
	DefaultOfflineThreshold = 5 * time.Minute
	DefaultReadTimeout      = 15 * time.Second
	DefaultWriteTimeout     = 15 * time.Second
	DefaultIdleTimeout      = 60 * time.Second
	DefaultShutdownTimeout  = 5 * time.Second
)

const legacyComposeDevJWTSecret = "default-dev-jwt-secret-key-min-32-bytes-secure!!"

// Config encapsulates configuration for the Go backend server.
type Config struct {
	AppEnv                   string
	Port                     string
	DatabaseURL              string
	PostgresSSLMode          string
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
	validationErr            error
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
		"Config{AppEnv:%s, Port:%s, DatabaseURLSet:%t, PostgresSSLMode:%s, MQTTHost:%s, MQTTPort:%s, MQTTBrokerURI:%s, JWTSecretKeyLen:%d, MasterKeySet:%t}",
		c.AppEnv,
		c.Port,
		c.DatabaseURL != "",
		c.PostgresSSLMode,
		sanitizeHost(c.MQTTHost),
		c.MQTTPort,
		redactURI(c.MQTTBrokerURI),
		len(c.JWTSecretKey),
		hasMasterKey,
	)
}

func parseAppEnv(raw string) (string, error) {
	trimmed := strings.ToLower(strings.TrimSpace(raw))
	switch trimmed {
	case "", "development", "dev", "local", "test":
		return EnvDevelopment, nil
	case "staging":
		return EnvStaging, nil
	case "production", "prod":
		return EnvProduction, nil
	default:
		return "", errors.New("invalid APP_ENV: must be development, staging, or production")
	}
}

func validatePostgresSSLMode(raw string) (string, error) {
	trimmed := strings.ToLower(strings.TrimSpace(raw))
	if trimmed == "" {
		return "", nil
	}
	switch trimmed {
	case "disable", "allow", "prefer", "require", "verify-ca", "verify-full":
		return trimmed, nil
	default:
		return "", errors.New("invalid POSTGRES_SSLMODE: must be one of disable, allow, prefer, require, verify-ca, verify-full")
	}
}

func applyPostgresSSLMode(dbURL, sslMode string) (string, error) {
	if dbURL == "" || sslMode == "" {
		return dbURL, nil
	}
	u, err := url.Parse(dbURL)
	if err != nil {
		return "", errors.New("invalid DATABASE_URL")
	}
	q := u.Query()
	if !q.Has("sslmode") {
		q.Set("sslmode", sslMode)
		u.RawQuery = q.Encode()
		return u.String(), nil
	}
	return dbURL, nil
}

func hasPlaceholderPrefix(val string) bool {
	return strings.HasPrefix(strings.ToUpper(strings.TrimSpace(val)), "REPLACE_WITH_")
}

func isInsecureJWTSecret(secret string) bool {
	return secret == DefaultJWTSecret ||
		secret == legacyComposeDevJWTSecret ||
		hasPlaceholderPrefix(secret)
}

func deriveProvisionMasterKey(jwtSecret string) [32]byte {
	return sha256.Sum256([]byte(jwtSecret + ":provision:master:key"))
}

func parseProvisionMasterKey(raw string) ([32]byte, error) {
	var key [32]byte
	if raw == "" {
		return key, errors.New("DEVICE_PROVISION_MASTER_KEY is required in production")
	}
	if hasPlaceholderPrefix(raw) {
		return key, errors.New("DEVICE_PROVISION_MASTER_KEY must not use placeholder value in production")
	}
	if len(raw) == 64 {
		decoded, err := hex.DecodeString(raw)
		if err != nil || len(decoded) != 32 {
			return key, errors.New("DEVICE_PROVISION_MASTER_KEY of length 64 must be valid hex")
		}
		copy(key[:], decoded)
	} else if len(raw) >= 32 {
		copy(key[:], []byte(raw[:32]))
	} else {
		return key, errors.New("DEVICE_PROVISION_MASTER_KEY must be 64 hex characters or at least 32 bytes")
	}
	if key == [32]byte{} {
		return [32]byte{}, errors.New("DEVICE_PROVISION_MASTER_KEY must not be all zeros")
	}
	return key, nil
}

func validateJWTSecret(secret string) error {
	if secret == "" {
		return errors.New("JWT_SECRET_KEY is required in production")
	}
	if strings.TrimSpace(secret) == "" {
		return errors.New("JWT_SECRET_KEY must not be blank in production")
	}
	if len(secret) < 32 {
		return errors.New("JWT_SECRET_KEY must be at least 32 bytes in production")
	}
	if isInsecureJWTSecret(secret) {
		return errors.New("JWT_SECRET_KEY must not use default or placeholder value in production")
	}
	return nil
}

// IsProduction returns true when APP_ENV is configured as production.
func (c *Config) IsProduction() bool {
	if c == nil {
		return false
	}
	env, err := parseAppEnv(c.AppEnv)
	return err == nil && env == EnvProduction
}

// RequiresStrictSecrets returns true when runtime mode requires fail-fast secret validation (production/staging).
func (c *Config) RequiresStrictSecrets() bool {
	if c == nil {
		return false
	}
	env, err := parseAppEnv(c.AppEnv)
	if err != nil {
		return true
	}
	return env == EnvProduction || env == EnvStaging
}

// Validate verifies environment mode, SSL settings, and production secret invariants without leaking secret values.
func (c *Config) Validate() error {
	if c == nil {
		return errors.New("config cannot be nil")
	}
	if c.validationErr != nil {
		return c.validationErr
	}

	var errs []error
	env, err := parseAppEnv(c.AppEnv)
	if err != nil {
		errs = append(errs, err)
	}
	if _, err := validatePostgresSSLMode(c.PostgresSSLMode); err != nil {
		errs = append(errs, err)
	}
	if env == EnvProduction || env == EnvStaging {
		if err := validateJWTSecret(c.JWTSecretKey); err != nil {
			errs = append(errs, err)
		}
		if c.DeviceProvisionMasterKey == [32]byte{} {
			errs = append(errs, errors.New("DEVICE_PROVISION_MASTER_KEY is required in production"))
		} else if c.DeviceProvisionMasterKey == deriveProvisionMasterKey(c.JWTSecretKey) ||
			c.DeviceProvisionMasterKey == deriveProvisionMasterKey(DefaultJWTSecret) {
			errs = append(errs, errors.New("DEVICE_PROVISION_MASTER_KEY must not be derived from JWT_SECRET_KEY in production"))
		}
	}
	return errors.Join(errs...)
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

// LoadWithError reads and validates backend configuration from OS environment variables.
func LoadWithError() (*Config, error) {
	return LoadFromEnvWithError(os.Getenv)
}

// LoadFromEnvWithError loads and validates configuration using a custom environment accessor.
func LoadFromEnvWithError(getEnv func(string) string, lookupHost ...LookupHostFunc) (*Config, error) {
	cfg := LoadFromEnv(getEnv, lookupHost...)
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return cfg, nil
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

	var errs []error

	rawAppEnv := getEnv("APP_ENV")
	appEnv, envErr := parseAppEnv(rawAppEnv)
	if envErr != nil {
		errs = append(errs, envErr)
		appEnv = strings.TrimSpace(rawAppEnv)
	}
	strictSecrets := envErr != nil || appEnv == EnvProduction || appEnv == EnvStaging

	port := getEnv("PORT")
	if port == "" {
		port = DefaultPort
	}

	sslMode, sslErr := validatePostgresSSLMode(getEnv("POSTGRES_SSLMODE"))
	if sslErr != nil {
		errs = append(errs, sslErr)
	}

	dbURL := getEnv("DATABASE_URL")
	if sslErr == nil {
		updatedDBURL, dbErr := applyPostgresSSLMode(dbURL, sslMode)
		if dbErr != nil {
			errs = append(errs, dbErr)
		} else {
			dbURL = updatedDBURL
		}
	}

	mqttHost := getEnv("MQTT_HOST")
	mqttPort := getEnv("MQTT_PORT")
	if mqttPort == "" {
		mqttPort = DefaultMQTTPort
	}

	jwtSecret := getEnv("JWT_SECRET_KEY")
	if strictSecrets {
		if err := validateJWTSecret(jwtSecret); err != nil {
			errs = append(errs, err)
			jwtSecret = ""
		}
	} else if len(jwtSecret) < 32 {
		jwtSecret = DefaultJWTSecret
	}

	var masterKey [32]byte
	provisionKeyEnv := getEnv("DEVICE_PROVISION_MASTER_KEY")
	parsedKey, keyErr := parseProvisionMasterKey(provisionKeyEnv)
	if keyErr == nil {
		masterKey = parsedKey
	} else if strictSecrets {
		errs = append(errs, keyErr)
	} else {
		masterKey = deriveProvisionMasterKey(jwtSecret)
	}

	return &Config{
		AppEnv:                   appEnv,
		Port:                     port,
		DatabaseURL:              dbURL,
		PostgresSSLMode:          sslMode,
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
		validationErr:            errors.Join(errs...),
	}
}
