# Deployment contexts

## Local development
- PostgreSQL and Mosquitto may be started using `deploy/compose.yaml`.
- The development MQTT listener is **localhost-only and explicitly insecure**, opt-in using Compose profile `dev-insecure`.
- Real Gateway access uses TLS with authenticated MQTT clients; provisioning setup is a separate security task.
- Database schema migrations are decoupled from `backend` container startup into the one-shot `migrate` service (`/app/migrate.sh`, profiles `fullstack`, `backend`, `migrate`) protected by a PostgreSQL session advisory lock (`pg_advisory_lock`) and `ON_ERROR_STOP=1` per-migration transactions.

## Staging / production
- TLS 1.2+ or 1.3 as supported, device identity + topic ACL, rotation and secrets injection.
- Private keys, certificates, passwords, database dumps, and realistic customer sensor records never enter Git.
- Restart policies, bounded CPU/memory limits (`deploy.resources`), and decoupled migrations are configured in `deploy/compose.yaml`:
  - Persistent runtime services (`postgres`, `mqtt-dev`, `mqtt-tls`, `backend`, `web-dashboard`) use `restart: unless-stopped`; the one-shot `migrate` runner uses `restart: "no"` with `backend` depending on `migrate: condition: service_completed_successfully`.
  - Resource limits (`postgres`: 1.0 CPU / 512 MiB; `mqtt-dev`: 0.5 CPU / 128 MiB; `mqtt-tls`: 0.5 CPU / 256 MiB; `migrate`: 0.5 CPU / 128 MiB; `backend`: 1.0 CPU / 256 MiB; `web-dashboard`: 1.0 CPU / 512 MiB) bound noisy-neighbor contention without starving PostgreSQL `shared_buffers`, Mosquitto persistence/TLS handshakes, or Go/Node runtimes under MVP load.
- Persistent state (`pg_data`, `mqtt_data`) and `pg_data` backup/restore exercises (`pg_dump -Fc` / `pg_restore` into an external host directory with `0700`/`0600` permissions and SHA-256 verification) are documented in [`deploy/README.md`](../../deploy/README.md).
- Do not deploy this scaffold as an operational IoT system without completing human security review, external CA/secrets provisioning, and host/network hardening.
