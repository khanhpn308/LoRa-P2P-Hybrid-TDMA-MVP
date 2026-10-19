# Backend Go

**Scaffold only.** Go executable currently logs that business services are not yet implemented. Run `go test ./...` and `go run ./cmd/server` locally. No API endpoint, scheduler, MQTT client or database is active.

Architecture target: modular monolith with `internal/{domain,mqtt,scheduler,telemetry,alert,api,storage}`.
