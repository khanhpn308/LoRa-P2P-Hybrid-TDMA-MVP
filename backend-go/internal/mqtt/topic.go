package mqtt

import (
	"errors"
	"fmt"
	"strings"
)

const (
	// TopicPrefixGw is the canonical MQTT 5.0 topic prefix for gateways.
	TopicPrefixGw = "iot/v1/gw/"
	// TopicSuffixJoinHello is the canonical MQTT 5.0 topic suffix for Join Hello uplink relay.
	TopicSuffixJoinHello = "/uplink/join-hello"
)

var (
	// ErrMalformedTopic indicates the topic does not match iot/v1/gw/{gateway_id}/uplink/join-hello.
	ErrMalformedTopic = errors.New("topic does not match canonical iot/v1/gw/{gateway_id}/uplink/join-hello format")
)

// BuildJoinHelloTopic formats the canonical Join Hello topic for a given gateway ID.
func BuildJoinHelloTopic(gatewayID string) string {
	return TopicPrefixGw + gatewayID + TopicSuffixJoinHello
}

// ParseJoinHelloTopic extracts and validates the gateway ID from a canonical Join Hello topic.
func ParseJoinHelloTopic(topic string) (string, error) {
	if len(topic) < len(TopicPrefixGw)+len(TopicSuffixJoinHello) ||
		!strings.HasPrefix(topic, TopicPrefixGw) ||
		!strings.HasSuffix(topic, TopicSuffixJoinHello) {
		return "", fmt.Errorf("%w: %q", ErrMalformedTopic, topic)
	}

	gatewayID := topic[len(TopicPrefixGw) : len(topic)-len(TopicSuffixJoinHello)]
	if gatewayID == "" || strings.Contains(gatewayID, "/") {
		return "", fmt.Errorf("%w: invalid gateway_id segment %q", ErrMalformedTopic, gatewayID)
	}

	if !regexGatewayID.MatchString(gatewayID) {
		return "", fmt.Errorf("%w: %w: %q", ErrMalformedTopic, ErrInvalidGatewayID, gatewayID)
	}

	return gatewayID, nil
}
