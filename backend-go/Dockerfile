# syntax=docker/dockerfile:1
# Stage 1: Build binary
FROM golang:1.27.3-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /server ./cmd/server

# Stage 2: Minimal runtime image
FROM alpine:3.24.3

RUN apk add --no-cache ca-certificates postgresql-client tzdata bash

WORKDIR /app

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

COPY --from=builder /server /app/server
COPY migrations /app/migrations

RUN cat <<'EOF' > /app/entrypoint.sh
#!/bin/sh
set -e

if [ -n "$DATABASE_URL" ]; then
  echo "Waiting for PostgreSQL to be ready..."
  MAX_RETRIES=30
  RETRIES=0
  until pg_isready -d "$DATABASE_URL" >/dev/null 2>&1; do
    RETRIES=$((RETRIES + 1))
    if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
      echo "Error: Timed out waiting for PostgreSQL to be ready."
      exit 1
    fi
    echo "PostgreSQL is unavailable - sleeping 1s ($RETRIES/$MAX_RETRIES)"
    sleep 1
  done
  echo "PostgreSQL is ready."

  echo "Checking and applying database migrations..."
  psql -d "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(128) PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW());"

  for f in $(ls -1 /app/migrations/*.up.sql 2>/dev/null | sort); do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    applied=$(psql -d "$DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM schema_migrations WHERE version = '$base';")
    if [ "$applied" = "0" ]; then
      echo "Applying migration: $base"
      psql -d "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
      psql -d "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "INSERT INTO schema_migrations (version) VALUES ('$base');"
    else
      echo "Migration $base already applied; skipping."
    fi
  done
  echo "All migrations applied successfully."
fi

exec "$@"
EOF

RUN chmod +x /app/entrypoint.sh /app/server && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["/app/server"]
