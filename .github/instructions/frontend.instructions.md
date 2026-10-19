---
applyTo: "clients/**"
---
# Client rules

Web: React + TypeScript; mobile: Flutter/Dart when scoped. The backend API contract (`contracts/api/openapi.yaml`) is authoritative for schema, but still DRAFT until its endpoints are implemented. Do not connect clients directly to MQTT or expose operator credentials/keys. RBAC checks MUST be enforced server-side, never solely through client-side UI state. Keep emergency notifications distinct from guaranteed delivery deadlines.
