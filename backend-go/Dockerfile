# syntax=docker/dockerfile:1
# Stage 1: Build binary
FROM golang:alpine AS builder

WORKDIR /app

COPY go.mod ./
COPY . .

# Support both OpenAPI standard /healthz and AC1 /api/v1/health in the compiled binary
RUN sed -i 's|mux.HandleFunc("GET /healthz", h.handleHealthz)|mux.HandleFunc("GET /healthz", h.handleHealthz)\n\tmux.HandleFunc("GET /api/v1/health", h.handleHealthz)|g' internal/api/health_handler.go

RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /server ./cmd/server

# Stage 2: Minimal runtime image
FROM alpine:latest

RUN apk add --no-cache ca-certificates postgresql-client tzdata bash

WORKDIR /app

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

COPY --from=builder /server /app/server
COPY migrations /app/migrations

RUN cat <<'EOF' > /app/entrypoint.sh
#!/bin/sh
set -eu

if [ -n "${DATABASE_URL:-}" ]; then
  echo "Waiting for PostgreSQL to be ready..."
  MAX_RETRIES=30
  RETRIES=0
  until pg_isready -d "$DATABASE_URL" >/dev/null 2>&1; do
    RETRIES=$((RETRIES + 1))
    if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
      echo "Error: Timed out waiting for PostgreSQL to be ready." >&2
      exit 1
    fi
    echo "PostgreSQL is unavailable - sleeping 1s ($RETRIES/$MAX_RETRIES)"
    sleep 1
  done
  echo "PostgreSQL is ready."
fi

exec "$@"
EOF

RUN cat <<'EOF' > /app/migrate.sh
#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "Error: DATABASE_URL must be set to run migrations." >&2
  exit 1
fi

echo "Waiting for PostgreSQL to be ready..."
MAX_RETRIES=30
RETRIES=0
until pg_isready -d "$DATABASE_URL" >/dev/null 2>&1; do
  RETRIES=$((RETRIES + 1))
  if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
    echo "Error: Timed out waiting for PostgreSQL to be ready." >&2
    exit 1
  fi
  echo "PostgreSQL is unavailable - sleeping 1s ($RETRIES/$MAX_RETRIES)"
  sleep 1
done
echo "PostgreSQL is ready."

# Fixed 64-bit advisory lock key for schema migration serialization.
LOCK_KEY=748291045239184721
SQL_FILE=$(mktemp /tmp/migrate.XXXXXX)
trap 'rm -f "$SQL_FILE"' EXIT

{
  echo "\\set ON_ERROR_STOP on"
  echo "SELECT pg_advisory_lock(${LOCK_KEY});"
  echo "CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(128) PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW());"
  for f in $(find /app/migrations -maxdepth 1 -type f -name '*.up.sql' | sort); do
    base=$(basename "$f")
    case "$base" in
      *[!A-Za-z0-9._-]*)
        echo "Error: unsafe migration filename: $base" >&2
        exit 1
        ;;
    esac
    cat <<SQL
BEGIN;
SELECT NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '${base}') AS needs_apply \\gset
\\if :needs_apply
\\echo Applying migration: ${base}
\\i /app/migrations/${base}
INSERT INTO schema_migrations (version) VALUES ('${base}');
\\else
\\echo Migration ${base} already applied; skipping.
\\endif
COMMIT;
SQL
  done
  echo "SELECT pg_advisory_unlock(${LOCK_KEY});"
} > "$SQL_FILE"

echo "Checking and applying database migrations under advisory lock..."
psql -d "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$SQL_FILE"
echo "All migrations checked/applied successfully."
EOF

RUN chmod +x /app/entrypoint.sh /app/migrate.sh /app/server && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["/app/server"]
