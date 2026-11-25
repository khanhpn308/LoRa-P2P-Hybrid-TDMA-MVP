# Local PostgreSQL and MQTT

This local integration sample requires Human Security Audit. MQTT 5.0 is
owner-accepted in ADR-0002. Topic permissions follow the Issue #14 draft in
[`contracts/mqtt/topics.md`](../contracts/mqtt/topics.md), whose cross-team
approval is still pending. No backend service or firmware is started here.

## Start PostgreSQL and optional dev broker

Run from the repository root with Docker Engine, Compose and OpenSSL:

```bash
cp .env.example .env
chmod 600 .env
# Edit .env and replace POSTGRES_PASSWORD with a unique local secret.
docker compose --env-file .env -f deploy/compose.yaml config -q
docker compose --env-file .env -f deploy/compose.yaml up -d --wait postgres
docker compose --env-file .env -f deploy/compose.yaml --profile dev-insecure up -d mqtt-dev
```

Missing or empty `POSTGRES_USER`, `POSTGRES_DB` or `POSTGRES_PASSWORD` stops
Compose interpolation. The template password must be replaced. `config -q`
validates without printing resolved credentials. Avoid plain `config` and
`docker inspect` output in shared logs.

All published ports bind `127.0.0.1`. The anonymous, cleartext dev broker uses
1883 and its own Docker network. Do not attach other workloads or real Gateways
to that network. TLS uses 8883; PostgreSQL uses 5432. Docker daemon/network
access remains privileged. Profiles select services to start; explicitly naming
a service also starts it without its profile flag.

`pg_data` persists PostgreSQL data. Changing `.env` does not rotate credentials
in an initialized database. Its healthcheck tests readiness, not application
authentication or migrations. For interactive queries, schema details, table truncation, and maintenance commands, see [`docs/development/POSTGRESQL_OPERATIONS_GUIDE.md`](../docs/development/POSTGRESQL_OPERATIONS_GUIDE.md).

## Provision local test certificates outside Git

For real devices, use a reviewed CA/provisioning process. These one-day
certificates are only for local testing. CA and client keys stay outside the
broker mount, under the already ignored `deploy/secrets/`. Never force-add that
directory. No key or certificate is supplied in Git.

```bash
umask 077
mkdir -p deploy/secrets/pki deploy/secrets/broker deploy/secrets/clients deploy/secrets/backend
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=local-test-ca \
  -keyout deploy/secrets/pki/ca.key -out deploy/secrets/broker/ca.crt
openssl req -new -newkey rsa:2048 -nodes -subj /CN=mqtt-tls \
  -addext 'subjectAltName=DNS:mqtt-tls,DNS:localhost,IP:127.0.0.1' \
  -addext 'extendedKeyUsage=serverAuth' \
  -keyout deploy/secrets/broker/server.key -out deploy/secrets/pki/server.csr
openssl x509 -req -in deploy/secrets/pki/server.csr -days 1 \
  -CA deploy/secrets/broker/ca.crt -CAkey deploy/secrets/pki/ca.key -CAcreateserial \
  -copy_extensions copy -out deploy/secrets/broker/server.crt
for identity in gw-a gw-b backend; do
  openssl req -new -newkey rsa:2048 -nodes -subj "/CN=$identity" \
    -addext 'extendedKeyUsage=clientAuth' \
    -keyout "deploy/secrets/clients/$identity.key" \
    -out "deploy/secrets/pki/$identity.csr"
  openssl x509 -req -in "deploy/secrets/pki/$identity.csr" -days 1 \
    -CA deploy/secrets/broker/ca.crt -CAkey deploy/secrets/pki/ca.key -CAcreateserial \
    -copy_extensions copy -out "deploy/secrets/clients/$identity.crt"
done
# Isolate backend credentials from gateway keys and ca.key (backend container runs as appuser/appgroup, gid 101 in Alpine).
cp deploy/secrets/broker/ca.crt deploy/secrets/clients/backend.crt deploy/secrets/clients/backend.key deploy/secrets/backend/
sudo chown -R "$(id -u):101" deploy/secrets/backend
chmod 750 deploy/secrets/backend
chmod 640 deploy/secrets/backend/*
# Mosquitto in the existing image reads as uid/gid 1883.
sudo chown -R "$(id -u):1883" deploy/secrets/broker
chmod 750 deploy/secrets/broker
chmod 640 deploy/secrets/broker/*
```

Set `MQTT_CERT_DIR=./secrets/broker` and `MQTT_BACKEND_CERT_DIR=./secrets/backend` in `.env`.
Relative paths resolve from `deploy/`; an absolute external path also works.
The broker mount must exist with readable `ca.crt`, `server.crt`, and `server.key`.
The backend mount must contain only `ca.crt`, `backend.crt`, and `backend.key` (never `ca.key` or Gateway keys).
Compose does not silently create a missing certificate directory.
Verify the broker hostname against its certificate SAN (`DNS:mqtt-tls`, `DNS:localhost`, `IP:127.0.0.1`). Do not use `--insecure`.

### Backend MQTT TLS / Authentication Environment Variables

| Variable | Default in `.env.example` / Compose | Description |
|---|---|---|
| `MQTT_HOST` | `mqtt-tls` | Broker hostname (`mqtt-tls` in Docker Compose `--profile tls`, `localhost` when running `backend-go` on host, `mqtt-dev` only for opt-in `dev-insecure`). Unresolved hosts fail closed (no hardcoded LAN IP fallback). |
| `MQTT_PORT` | `8883` (`1883` when TLS disabled) | Broker port. |
| `MQTT_TLS_ENABLED` | `true` | Enables `tls://` scheme and TLS 1.2+ verification; fails closed if invalid or if cert files are missing/unreadable. |
| `MQTT_BACKEND_CERT_DIR` | `./secrets/backend` | Host directory bound read-only to `/run/secrets/mqtt` in the `backend` container. |
| `MQTT_TLS_CA_FILE` | `/run/secrets/mqtt/ca.crt` | Required PEM CA certificate path when TLS is enabled. |
| `MQTT_TLS_CERT_FILE` | `/run/secrets/mqtt/backend.crt` | Client certificate PEM path for mTLS (must be paired with `MQTT_TLS_KEY_FILE`). |
| `MQTT_TLS_KEY_FILE` | `/run/secrets/mqtt/backend.key` | Client private key PEM path for mTLS (must be paired with `MQTT_TLS_CERT_FILE`). |
| `MQTT_TLS_SERVER_NAME` | *(unset)* | Optional TLS SNI / server hostname override. |
| `MQTT_USERNAME` | *(unset)* | Optional MQTT username (for username/password broker auth). |
| `MQTT_PASSWORD` | *(unset)* | Optional MQTT password (requires `MQTT_USERNAME`; never logged or committed). |

```bash
docker compose --env-file .env -f deploy/compose.yaml --profile tls up -d --build mqtt-tls
docker compose --env-file .env -f deploy/compose.yaml logs mqtt-tls
```

TLS requires a trusted client certificate and TLS 1.2 or newer. Mosquitto uses
the verified certificate CN as its ACL username. Caller-supplied MQTT usernames
or ClientIDs cannot replace it. The sample [`mosquitto/acl`](mosquitto/acl) grants
`gw-a` and `gw-b` only their five named uplink writes and two named downlink
reads. `backend` has the inverse directions across Gateway identities. Unknown
CNs and other topics have no topic permissions. A trusted unknown CN may connect
but cannot read or write data. Backend certificate issuance is privileged
because that identity can publish downlinks to all Gateways.

Add new CNs only with reviewed explicit Gateway ACL blocks. Provisioning must
bind a unique CN to each device, reject duplicate identities and protect client
keys. The broker enforces topic access. Payload/topic identity, schema, expiry,
retain policy and application authorization remain application responsibilities.
`mqtt_data` persists broker state. Session/queue limits, revocation, rotation,
CA policy, backups, resource limits and remote deployment require review before
use beyond local testing.

The TLS image builds from `deploy/mosquitto/`. Its build context allows only the
Dockerfile, ACL and TLS configuration. It contains no certificate or private key.
The ACL is owned by `1883:1883` with mode `0600`, and the broker runs as that
non-root UID/GID. Rebuild with `--build` after changing ACL/configuration. The
broker mount must contain only the public CA, server certificate and server key;
never mount a CA private key or client keys there. The smoke test mounts each
client's CA and its own certificate/key as individual read-only files. Anonymous
clients receive only the public CA. Client keys remain mode `0600` on the host.

## Checks and cleanup

```bash
python3 scripts/verify_no_secrets.py
python3 -m unittest discover -s tests/integration -p test_verify_no_secrets.py -v
python3 -m unittest discover -s tests/integration -p test_infra_security.py -v
python3 -u tests/integration/test_local_infra.py
```

The Docker test uses random loopback ports, a unique Compose project and ignored
one-day test keys. It prints separate results and broker logs for health,
persistence, credential isolation, broker ownership, positive MQTT flows,
authentication failures and ACL denials. A separate Docker bridge client must
reach a temporary non-loopback host listener, then fail to reach each published
service on that same host address. Localhost service connections must succeed.
This Linux test needs `ip` from iproute2 and a usable non-loopback host IPv4; it
fails rather than skipping the check if no address or control path is available. It
removes only its own containers, volumes and temporary keys after completion or
a failed assertion. See [`tests/integration/README.md`](../tests/integration/README.md).

The secret check examines tracked worktree and index files plus added staged
and unstaged diff lines. It rejects `.env` variants except `.env.example`, key
container paths, tracked `secrets/` paths, PEM private key blocks and literal
PostgreSQL/MQTT password assignments. Public certificates in ordinary paths are
allowed; they contain no private key. Output contains locations and reasons
only. This is not an arbitrary-secret detector or a full-history scan. Run it
again after staging. Ignored and untracked local secret files are not read.

## Stop and cleanup

Stop the manually started project, preserving data:

```bash
docker compose --env-file .env -f deploy/compose.yaml --profile tls --profile dev-insecure --profile fullstack down
```

Adding `-v` permanently deletes that project's database and MQTT volumes. Remove
local test certificates and `.env` only when no longer needed. Do not delete
shared CA material.

## Full-stack Containerization (Backend & Web Dashboard)

Issue #266 integrates full-stack containerization for local execution and end-to-end verification:
- **`backend`**: Go Modular Monolith (`backend-go`), multi-stage Alpine build, non-root user (`appuser:appgroup`), automated PostgreSQL schema migrations, exposed at `127.0.0.1:8080`.
- **`web-dashboard`**: Next.js 16 standalone output (`clients/web-dashboard`), multi-stage Node 22 Alpine build, non-root user (`nextjs:nodejs`), exposed at `127.0.0.1:3000`.

### Start Full-stack with Docker Compose

Ensure `.env` is configured with `POSTGRES_PASSWORD`, `POSTGRES_USER`, and `POSTGRES_DB`:

```bash
# 1. Build frontend với API URL mới (hoặc khi thay đổi NEXT_PUBLIC_API_URL):
docker compose --env-file .env -f deploy/compose.yaml build web-dashboard

# 2. Khởi chạy toàn bộ hệ thống với MQTT TLS (PostgreSQL, MQTT TLS, Backend, Frontend):
docker compose --env-file .env -f deploy/compose.yaml --profile fullstack --profile tls up -d

# Hoặc opt-in dev-insecure (cần đặt MQTT_HOST=mqtt-dev, MQTT_PORT=1883, MQTT_TLS_ENABLED=false trong .env):
docker compose --env-file .env -f deploy/compose.yaml --profile fullstack --profile dev-insecure up -d

# 3. Kiểm tra trạng thái và sức khỏe các container:
docker compose --env-file .env -f deploy/compose.yaml ps

# Xem log Backend & migrations:
docker compose --env-file .env -f deploy/compose.yaml logs -f backend

# Xem log Web Dashboard:
docker compose --env-file .env -f deploy/compose.yaml logs -f web-dashboard
```

> [!NOTE]
> Trong cấu hình `deploy/compose.yaml`, `backend` mặc định kết nối bảo mật tới `mqtt-tls:8883` bằng mTLS (`MQTT_TLS_ENABLED=true`, mount read-only `./secrets/backend` tại `/run/secrets/mqtt`).
> Nếu chỉ chạy `--profile fullstack`, Docker chỉ khởi chạy `postgres`, `backend` và `web-dashboard` (chưa có `mqtt-tls`).
> Hãy chạy kèm `--profile tls` sau khi đã cấp phát chứng chỉ cục bộ ở bước trên:
> ```bash
> docker compose --env-file .env -f deploy/compose.yaml --profile fullstack --profile tls up -d
> ```

### External & LAN Access (Dev Opt-in) vs Production Reverse Proxy

Mặc định `deploy/compose.yaml` bind toàn bộ dịch vụ về loopback (`127.0.0.1:8080`, `127.0.0.1:3000`, `127.0.0.1:5432`) và không chứa literal secret fallback.

#### Chạy sau Reverse Proxy HTTPS / WSS (Port 443)
Trong môi trường staging/production, dùng `reverse-proxy` (Nginx TLS 1.2/1.3 termination trên cổng `443`) và file overlay `deploy/reverse-proxy/compose.prod.yaml` để chạy `APP_ENV=production`, bắt buộc `JWT_SECRET_KEY` và `DEVICE_PROVISION_MASTER_KEY`, đồng thời khóa `backend`, `web-dashboard`, `postgres` chỉ giao tiếp nội bộ trên Docker network:

1. Chuẩn bị chứng chỉ TLS (không commit vào Git) tại `deploy/secrets/proxy/` (`server.crt`, `server.key`) và cấu hình file env ngoài Git (ví dụ `.env.prod` với `chmod 600`):
   - `APP_ENV=production`
   - `JWT_SECRET_KEY` (>= 32 bytes ngẫu nhiên, ví dụ `openssl rand -base64 32`)
   - `DEVICE_PROVISION_MASTER_KEY` (64 ký tự hex ngẫu nhiên, ví dụ `openssl rand -hex 32`)
   - `POSTGRES_SSLMODE=require` hoặc `verify-full` (khi dùng PostgreSQL bên ngoài qua `DATABASE_URL`)
   - `NEXT_PUBLIC_API_URL=https://<your-domain-or-host>`
   - `PROXY_CERT_DIR=./secrets/proxy`
2. Kiểm tra cấu hình và khởi chạy:
   ```bash
   docker compose --env-file .env.prod -f deploy/compose.yaml -f deploy/reverse-proxy/compose.prod.yaml \
     --profile fullstack --profile reverse-proxy config -q
   docker compose --env-file .env.prod -f deploy/compose.yaml -f deploy/reverse-proxy/compose.prod.yaml \
     --profile fullstack --profile reverse-proxy up -d --build
   ```
   Nginx trên cổng `443` sẽ terminate TLS cho cả HTTPS (`/api/v1/`, `/healthz` -> `backend:8080`; `/` -> `web-dashboard:3000`) và WSS (`/api/v1/ws/realtime` -> `backend:8080`).

#### External & LAN Access (Laptop & Mobile trong mạng nội bộ Dev)
Chỉ dùng cho phát triển cục bộ khi cần truy cập từ thiết bị cùng mạng Wi-Fi/LAN:
1. Cấu hình biến môi trường trong file `.env`:
   - `NEXT_PUBLIC_API_URL=http://<LAN_IP>:8080` (ví dụ `http://192.168.88.113:8080`).
   - `BACKEND_PORT_BIND=0.0.0.0:8080`
   - `WEB_PORT_BIND=0.0.0.0:3000`
   - *(Lưu ý: Luôn giữ `POSTGRES_PORT_BIND=127.0.0.1:5432` để bảo mật CSDL)*.
2. Build lại frontend và khởi chạy:
   ```bash
   docker compose --env-file .env -f deploy/compose.yaml build web-dashboard
   docker compose --env-file .env -f deploy/compose.yaml --profile fullstack up -d
   ```
3. Mở cổng trên Windows Defender Firewall (chạy PowerShell quyền Administrator trên Windows):
   ```powershell
   New-NetFirewallRule -DisplayName "WSL-Docker-Inbound" -Direction Inbound -LocalPort 3000,8080,1883,8883 -Protocol TCP -Action Allow
   New-NetFirewallHyperVRule -Name "WSL Docker" -DisplayName "WSL Docker" -Direction Inbound -LocalPorts 3000,8080,1883,8883 -Protocol TCP -Action Allow
   ```
4. Địa chỉ truy cập:
   - **Từ chính máy tính laptop:** `http://localhost:3000`
   - **Từ thiết bị bên ngoài (Điện thoại/Tablet cùng mạng Wi-Fi):** `http://<LAN_IP>:3000` (ví dụ `http://192.168.88.113:3000`)

### Stop Full-stack Services

```bash
# Dừng full-stack (PostgreSQL, Backend, Frontend):
docker compose --env-file .env -f deploy/compose.yaml --profile fullstack down

# Dừng và dọn dẹp toàn bộ (PostgreSQL, MQTT TLS/Dev, Backend, Frontend):
docker compose --env-file .env -f deploy/compose.yaml --profile tls --profile dev-insecure --profile fullstack down
```
To also remove persistent database and broker volumes, append `-v`.


Human Security Audit still needs to assess CA issuance/revocation/rotation,
Backend identity privileges, Docker daemon/network access and deployment on the
intended host. The non-loopback probe runs inside a separate Docker network on
the tested host. It does not replace tests from physical LAN/Internet clients,
IPv6 checks or firewall/direct-routing review. Docker documents localhost port
exposure on releases older than 28.0.0; use a supported patched engine and verify
the deployment network independently.

Sources: [Mosquitto authentication and ACL configuration](https://mosquitto.org/man/mosquitto-conf-5.html),
[Compose profiles](https://docs.docker.com/compose/how-tos/profiles/),
[Compose required environment variables](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/),
[Docker port publishing and direct-routing limits](https://docs.docker.com/engine/network/port-publishing/).
