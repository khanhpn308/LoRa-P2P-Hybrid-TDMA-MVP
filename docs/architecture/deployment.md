# Deployment contexts

## Local development
- PostgreSQL and Mosquitto may be started using `deploy/compose.yaml`.
- The development MQTT listener is **localhost-only and explicitly insecure**, opt-in using Compose profile `dev-insecure`.
- Real Gateway access uses TLS with authenticated MQTT clients; provisioning setup is a separate security task.

## Staging / production
- TLS 1.2+ or 1.3 as supported, device identity + topic ACL, rotation and secrets injection.
- Backend runtime mode `APP_ENV=production` fails fast on startup when `JWT_SECRET_KEY` (< 32 bytes or default/placeholder) or `DEVICE_PROVISION_MASTER_KEY` is missing or invalid.
- Production deployments terminate HTTPS and WSS on port `443` via the Nginx `reverse-proxy` (`deploy/reverse-proxy/nginx.conf` + `deploy/reverse-proxy/compose.prod.yaml`), keeping `backend:8080`, `web-dashboard:3000`, and PostgreSQL on the internal Docker network with no direct host port exposure.
- External PostgreSQL deployments must configure TLS via `POSTGRES_SSLMODE` (`require` or `verify-full`) or `DATABASE_URL` instead of hardcoded `sslmode=disable`.
- Private keys, certificates, passwords and realistic customer sensor records never enter Git.
- Set up resource limits, restart, backup/restore exercises and persistent state design.
- Do not deploy this scaffold as an operational IoT system without completing human security review.
