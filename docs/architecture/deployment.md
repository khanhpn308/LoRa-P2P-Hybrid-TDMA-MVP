# Deployment contexts

## Local development
- PostgreSQL and Mosquitto may be started using `deploy/compose.yaml`.
- The development MQTT listener is **localhost-only and explicitly insecure**, opt-in using Compose profile `dev-insecure`.
- Real Gateway access uses TLS with authenticated MQTT clients; provisioning setup is a separate security task.

## Staging / production
- TLS 1.2+ or 1.3 as supported, device identity + topic ACL, rotation and secrets injection.
- Private keys, certificates, passwords and realistic customer sensor records never enter Git.
- Set up resource limits, restart, backup/restore exercises and persistent state design.
- Do not deploy this scaffold as an operational IoT system. Zero active radio/device business logic is implemented.
