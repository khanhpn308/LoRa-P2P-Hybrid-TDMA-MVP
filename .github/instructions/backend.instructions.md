---
applyTo: "backend-go/**"
---
# Go backend rules

Keep a modular monolith: api, mqtt, scheduler, telemetry, alert, storage, domain. Use context cancellation, bounded concurrent work, graceful shutdown, safe configuration and explicit SQL migrations. Make MQTT QoS 1 ingestion idempotent with stable event/session identity, not just an 8-bit sequence number.

Go computes versioned future schedules; Gateway verifies/activates at superframe boundaries. No synchronous Go->MQTT calls in a slot-ISR control loop. Keep contracts and PostgreSQL migrations in step with API changes; no secrets in config or logging.
