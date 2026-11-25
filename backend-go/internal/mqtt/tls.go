package mqtt

import (
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"log"
	"net/url"
	"os"
	"strings"
	"time"

	paho "github.com/eclipse/paho.mqtt.golang"
)

// ErrInvalidTLSConfig indicates missing, unreadable, or invalid MQTT TLS/authentication settings.
var ErrInvalidTLSConfig = errors.New("invalid MQTT TLS/auth configuration")

// ClientAuthOptions configures TLS (including mTLS) and/or MQTT username/password authentication.
type ClientAuthOptions struct {
	TLSEnabled bool
	TLSConfig  *tls.Config
	CAFile     string
	CertFile   string
	KeyFile    string
	ServerName string
	Username   string
	Password   string
}

// SubscriberOption configures optional behavior on GatewayStatusSubscriber.
type SubscriberOption func(*GatewayStatusSubscriber)

// WithTLSConfig configures a pre-validated *tls.Config for the MQTT subscriber.
func WithTLSConfig(tlsCfg *tls.Config) SubscriberOption {
	return func(s *GatewayStatusSubscriber) {
		s.auth.TLSEnabled = true
		s.auth.TLSConfig = tlsCfg
	}
}

// WithClientAuth configures TLS and/or username/password authentication for the MQTT subscriber.
func WithClientAuth(auth ClientAuthOptions) SubscriberOption {
	return func(s *GatewayStatusSubscriber) {
		s.auth = auth
	}
}

// WithCredentials configures MQTT username/password authentication for the MQTT subscriber.
func WithCredentials(username, password string) SubscriberOption {
	return func(s *GatewayStatusSubscriber) {
		s.auth.Username = username
		s.auth.Password = password
	}
}

// redactBrokerURI strips password credentials from broker URIs before logging.
func redactBrokerURI(raw string) string {
	if raw == "" {
		return ""
	}
	u, err := url.Parse(raw)
	if err != nil {
		return "[redacted-uri]"
	}
	return u.Redacted()
}

// BuildTLSConfig constructs and validates a fail-closed *tls.Config from ClientAuthOptions.
func BuildTLSConfig(auth ClientAuthOptions) (*tls.Config, error) {
	if auth.TLSConfig != nil {
		if auth.TLSConfig.InsecureSkipVerify {
			return nil, fmt.Errorf("%w: InsecureSkipVerify is prohibited", ErrInvalidTLSConfig)
		}
		if auth.TLSConfig.RootCAs == nil {
			return nil, fmt.Errorf("%w: RootCAs must be configured for TLS verification", ErrInvalidTLSConfig)
		}
		cloned := auth.TLSConfig.Clone()
		if cloned.MinVersion < tls.VersionTLS12 {
			cloned.MinVersion = tls.VersionTLS12
		}
		cloned.InsecureSkipVerify = false
		if name := strings.TrimSpace(auth.ServerName); name != "" {
			cloned.ServerName = name
		}
		return cloned, nil
	}

	caFile := strings.TrimSpace(auth.CAFile)
	if caFile == "" {
		return nil, fmt.Errorf("%w: CA certificate file is required when TLS is enabled", ErrInvalidTLSConfig)
	}
	caPEM, err := os.ReadFile(caFile)
	if err != nil {
		return nil, fmt.Errorf("%w: failed to read CA certificate file %q: %v", ErrInvalidTLSConfig, caFile, err)
	}
	caPool := x509.NewCertPool()
	if !caPool.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("%w: CA certificate file %q contains no valid PEM certificates", ErrInvalidTLSConfig, caFile)
	}

	tlsCfg := &tls.Config{
		MinVersion:         tls.VersionTLS12,
		RootCAs:            caPool,
		InsecureSkipVerify: false,
		ServerName:         strings.TrimSpace(auth.ServerName),
	}

	certFile := strings.TrimSpace(auth.CertFile)
	keyFile := strings.TrimSpace(auth.KeyFile)
	if (certFile != "") != (keyFile != "") {
		return nil, fmt.Errorf("%w: both client certificate and key files must be provided for mTLS", ErrInvalidTLSConfig)
	}
	if certFile != "" && keyFile != "" {
		if _, err := os.Stat(certFile); err != nil {
			return nil, fmt.Errorf("%w: client certificate file %q is not accessible: %v", ErrInvalidTLSConfig, certFile, err)
		}
		if _, err := os.Stat(keyFile); err != nil {
			return nil, fmt.Errorf("%w: client key file %q is not accessible: %v", ErrInvalidTLSConfig, keyFile, err)
		}
		cert, err := tls.LoadX509KeyPair(certFile, keyFile)
		if err != nil {
			return nil, fmt.Errorf("%w: failed to load client certificate/key pair: %v", ErrInvalidTLSConfig, err)
		}
		tlsCfg.Certificates = []tls.Certificate{cert}
	}

	return tlsCfg, nil
}

func (s *GatewayStatusSubscriber) buildClientOptions() (*paho.ClientOptions, error) {
	if strings.TrimSpace(s.brokerURI) == "" {
		return nil, fmt.Errorf("%w: broker URI is empty", ErrInvalidTLSConfig)
	}
	u, err := url.Parse(s.brokerURI)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return nil, fmt.Errorf("%w: invalid broker URI %q", ErrInvalidTLSConfig, redactBrokerURI(s.brokerURI))
	}

	if s.auth.Password != "" && s.auth.Username == "" {
		return nil, fmt.Errorf("%w: MQTT password supplied without username", ErrInvalidTLSConfig)
	}

	opts := paho.NewClientOptions()
	opts.AddBroker(s.brokerURI)
	opts.SetClientID(fmt.Sprintf("backend-sub-%d", time.Now().UnixNano()%100000))
	opts.SetAutoReconnect(true)
	opts.SetConnectTimeout(5 * time.Second)
	opts.SetKeepAlive(30 * time.Second)

	scheme := strings.ToLower(u.Scheme)
	switch scheme {
	case "tls", "ssl", "tcps":
		tlsCfg, err := BuildTLSConfig(s.auth)
		if err != nil {
			return nil, err
		}
		opts.SetTLSConfig(tlsCfg)
	case "tcp":
		if s.auth.TLSEnabled || s.auth.TLSConfig != nil ||
			strings.TrimSpace(s.auth.CAFile) != "" ||
			strings.TrimSpace(s.auth.CertFile) != "" ||
			strings.TrimSpace(s.auth.KeyFile) != "" {
			return nil, fmt.Errorf("%w: TLS configuration requires tls:// broker URI (got tcp://)", ErrInvalidTLSConfig)
		}
	default:
		return nil, fmt.Errorf("%w: unsupported MQTT broker URI scheme %q", ErrInvalidTLSConfig, u.Scheme)
	}

	if s.auth.Username != "" {
		opts.SetUsername(s.auth.Username)
	}
	if s.auth.Password != "" {
		opts.SetPassword(s.auth.Password)
	}

	safeURI := redactBrokerURI(s.brokerURI)
	opts.SetOnConnectHandler(func(c paho.Client) {
		log.Printf("[MQTT Subscriber] Connected to broker %s; registering subscriptions...", safeURI)
		// 1. Gateway Status
		c.Subscribe("iot/v1/gw/+/uplink/status", 1, s.handleMessage)
		// 2. Node Events / Alerts
		c.Subscribe("iot/v1/gw/+/uplink/alert", 1, s.handleAlertMessage)
		// 3. Node Join Requests
		c.Subscribe("iot/v1/gw/+/uplink/join-hello", 1, s.handleJoinMessage)
		c.Subscribe("iot/v1/gw/+/uplink/join-request", 1, s.handleJoinMessage)
		// 4. Binary Heartbeat & Node Liveness Bitmap
		c.Subscribe("iot/v1/gw/+/uplink/heartbeat", 1, s.handleHeartbeatMessage)
		// 5. LoRa RF Metrics (Issue #392 / #393)
		c.Subscribe("iot/v1/gw/+/uplink/rf-metrics", 1, s.handleRFMetricsMessage)
	})

	opts.SetConnectionLostHandler(func(c paho.Client, err error) {
		log.Printf("[MQTT Subscriber] Broker connection lost: %v", err)
	})

	return opts, nil
}
