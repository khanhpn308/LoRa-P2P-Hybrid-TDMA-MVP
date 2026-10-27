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
authentication or migrations.

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
docker compose --env-file .env -f deploy/compose.yaml --profile tls up -d mqtt-tls
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
use beyond local testing. Mosquitto 2.0 may warn about ownership of the read-only
source ACL mount. Review future-image ownership requirements before upgrading.

## Checks and cleanup

```bash
python3 scripts/verify_no_secrets.py
python3 -m unittest discover -s tests/integration -p test_verify_no_secrets.py -v
python3 -u tests/integration/test_local_infra.py
```

The Docker test uses random loopback ports, a unique Compose project and ignored
one-day test keys. It prints separate results and broker logs for health,
persistence, positive MQTT flows, authentication failures and ACL denials. It
removes only its own containers, volumes and temporary keys after completion or
a failed assertion. See [`tests/integration/README.md`](../tests/integration/README.md).

The secret check examines tracked worktree and index files plus added staged
and unstaged diff lines. It rejects `.env` variants except `.env.example`, key
container paths, tracked `secrets/` paths, PEM private key blocks and literal
PostgreSQL/MQTT password assignments. Public certificates in ordinary paths are
allowed; they contain no private key. Output contains locations and reasons
only. This is not an arbitrary-secret detector or a full-history scan. Run it
again after staging. Ignored and untracked local secret files are not read.

Stop the manually started project, preserving data:

```bash
docker compose --env-file .env -f deploy/compose.yaml --profile tls --profile dev-insecure down
```

Adding `-v` permanently deletes that project's database and MQTT volumes. Remove
local test certificates and `.env` only when no longer needed. Do not delete
shared CA material.

Sources: [Mosquitto authentication and ACL configuration](https://mosquitto.org/man/mosquitto-conf-5.html),
[Compose profiles](https://docs.docker.com/compose/how-tos/profiles/),
[Compose required environment variables](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/).
