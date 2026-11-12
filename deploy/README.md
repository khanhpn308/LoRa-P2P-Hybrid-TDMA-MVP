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
mkdir -p deploy/secrets/pki deploy/secrets/broker deploy/secrets/clients
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=local-test-ca \
  -keyout deploy/secrets/pki/ca.key -out deploy/secrets/broker/ca.crt
openssl req -new -newkey rsa:2048 -nodes -subj /CN=localhost \
  -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' \
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
# Mosquitto in the existing image reads as uid/gid 1883.
sudo chown -R "$(id -u):1883" deploy/secrets/broker
chmod 750 deploy/secrets/broker
chmod 640 deploy/secrets/broker/*
```

Set `MQTT_CERT_DIR=./secrets/broker` in `.env`. Relative paths resolve from
`deploy/`; an absolute external path also works. The directory must exist with
readable `ca.crt`, `server.crt`, and `server.key`. Compose does not silently create
a missing certificate directory. Each client needs its own certificate/key and
the public CA certificate. Verify the broker hostname against its certificate
SAN. Do not use `--insecure`.

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

# 2. Khởi chạy toàn bộ hệ thống (PostgreSQL, Backend, Frontend):
docker compose --env-file .env -f deploy/compose.yaml --profile fullstack up -d

# Hoặc khởi chạy toàn bộ hệ thống gồm cả MQTT Broker (PostgreSQL, MQTT, Backend, Frontend):
docker compose --env-file .env -f deploy/compose.yaml --profile fullstack --profile dev-insecure up -d

# 3. Kiểm tra trạng thái và sức khỏe các container:
docker compose --env-file .env -f deploy/compose.yaml ps

# Xem log Backend & migrations:
docker compose --env-file .env -f deploy/compose.yaml logs -f backend

# Xem log Web Dashboard:
docker compose --env-file .env -f deploy/compose.yaml logs -f web-dashboard
```

> [!NOTE]
> Trong cấu hình `deploy/compose.yaml`, container `backend` tự động kết nối tới MQTT Broker (`mqtt-dev:1883`) để lắng nghe trạng thái Gateway.
> Nếu chỉ chạy `--profile fullstack`, Docker chỉ khởi chạy `postgres`, `backend` và `web-dashboard` (chưa có `mqtt-dev`).
> Để khởi chạy toàn bộ hệ thống gồm cả Backend, Web Dashboard, PostgreSQL **và MQTT Broker**:
> ```bash
> docker compose --env-file .env -f deploy/compose.yaml --profile fullstack --profile dev-insecure up -d
> ```

### External & LAN Access (Laptop & Mobile)

Khi cần truy cập từ các thiết bị ngoài trong cùng mạng Wi-Fi/LAN (điện thoại, ESP32 Gateway):
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
