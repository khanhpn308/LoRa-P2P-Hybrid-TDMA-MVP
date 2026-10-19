# Local services and secure provisioning

Copy `.env.example` to `.env`, replace the password with a local-only secret, then:
```bash
docker compose --env-file .env -f deploy/compose.yaml up -d postgres
# Optional INSECURE localhost development broker (not for any real remote Gateway)
docker compose --env-file .env -f deploy/compose.yaml --profile dev-insecure up -d mqtt-dev
```

TLS MQTT is an opt-in blueprint (`--profile tls`) and requires `deploy/secrets/ca.crt`, `server.crt`, `server.key` (never committed) and device client certificate provisioning. Configure ACL / identity and validate permissions before use. The bootstrap backend has no running HTTP service, so it is deliberately not included as a production-looking container.

Production requires hardening, secured secrets, storage, health checks, backups and documented threat-model review. Local development listener 1883 is unencrypted: do not expose to networks.
