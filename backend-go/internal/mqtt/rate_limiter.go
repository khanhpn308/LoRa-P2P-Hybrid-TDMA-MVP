package mqtt

import (
	"context"
	"errors"
	"sync"
	"time"
)

var (
	// ErrRateLimited indicates the request rate exceeded the configured threshold.
	ErrRateLimited = errors.New("rate limit exceeded for identifier")
)

// RateLimiter bounds incoming message rates per key (e.g. gateway ID or device MAC).
type RateLimiter interface {
	Allow(ctx context.Context, key string) bool
}

// TokenBucketLimiter implements a thread-safe token bucket rate limiter.
type TokenBucketLimiter struct {
	mu         sync.Mutex
	capacity   float64
	refillRate float64 // tokens per second
	buckets    map[string]*bucket
}

type bucket struct {
	tokens     float64
	lastRefill time.Time
}

// NewTokenBucketLimiter creates a TokenBucketLimiter with given capacity and refill rate.
func NewTokenBucketLimiter(capacity, refillRate float64) *TokenBucketLimiter {
	return &TokenBucketLimiter{
		capacity:   capacity,
		refillRate: refillRate,
		buckets:    make(map[string]*bucket),
	}
}

// Allow returns true if a token is available for the given key, consuming one token.
func (l *TokenBucketLimiter) Allow(ctx context.Context, key string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := time.Now()
	b, ok := l.buckets[key]
	if !ok {
		l.buckets[key] = &bucket{
			tokens:     l.capacity - 1,
			lastRefill: now,
		}
		return true
	}

	elapsed := now.Sub(b.lastRefill).Seconds()
	b.tokens += elapsed * l.refillRate
	if b.tokens > l.capacity {
		b.tokens = l.capacity
	}
	b.lastRefill = now

	if b.tokens >= 1.0 {
		b.tokens -= 1.0
		return true
	}

	return false
}

// NoopRateLimiter is a rate limiter that allows all requests (for testing/unrestricted).
type NoopRateLimiter struct{}

// Allow always returns true.
func (n *NoopRateLimiter) Allow(ctx context.Context, key string) bool {
	return true
}
