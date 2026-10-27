# Local infrastructure integration tests

Run from the repository root:

```bash
python3 -m unittest discover -s tests/integration -p test_verify_no_secrets.py -v
python3 -m unittest discover -s tests/integration -p test_infra_security.py -v
python3 -u tests/integration/test_local_infra.py
```

Secret scanner tests use disposable Git repositories and synthetic markers.
The real infrastructure test requires a local Linux Docker Engine, Compose,
OpenSSL, Python 3, iproute2's `ip` command, a non-loopback host IPv4 address,
and the existing `postgres:16-alpine` and `eclipse-mosquitto:2.0` images. It starts
the deployment configuration with random localhost ports, a unique project,
temporary volumes, and one-day certificates under ignored
`tests/integration/secrets/`. Keys and resolved configuration never appear in
logs. An owner-only parent directory protects test material on the host;
each client runs as the host UID/GID and receives individual read-only mounts
of the public CA and its own mode-0600 key/certificate. The anonymous client
gets only the public CA. Runtime file listings assert these boundaries for all
identities, and a unit regression test checks the exact mount sources.

The broker receives a separate directory containing only the public CA and
server certificate/key. A short-lived root provisioning container changes only
that directory's group to 1883, preserving host ownership for cleanup; it never
receives the CA private key or client keys. Broker directory mode is 0750 and
files are 0640. The TLS image copies its non-secret ACL as uid/gid 1883 with
mode 0600 and runs non-root. The test checks the runtime UID, ACL ownership/mode
and absence of startup/ownership warnings.

The test checks required environment validation, dev network separation,
loopback port bindings, positive localhost connections and negative non-loopback
reachability for PostgreSQL and both brokers, database persistence across recreation, broker
hostname verification, MQTT 5 QoS1 flows for both Gateways and Backend, missing
and untrusted certificate rejection, and publish/read permissions. It includes
ClientID/username spoofing, unknown CNs, role reversal, unlisted topics and a
wildcard subscription. Unauthorized publishes must report MQTT 5 PUBACK reason
135. Mosquitto may accept unauthorized subscriptions while filtering delivery.
Those checks require a bounded receive timeout with no payload, after positive
delivery checks for the same topics. Payloads are transport probes, not schema
fixtures. For each eligible host IPv4 address, a probe container on the separate
default bridge must first connect to a temporary control listener. It must then
fail to connect to each published service on that same address. Missing usable
addresses or a failed control connection fails the test, never records PASS.

Output includes separate assertions and broker logs; a failed assertion exits
nonzero. Subprocesses and waits are bounded. Cleanup removes only the generated
project, volumes and the generated broker image. Abrupt termination or a Docker daemon failure can require
manual cleanup using the project name printed in the broker logs.

These are local regression checks pending Human Security Audit. They do not
certify the draft MQTT contract, application semantics, integrated Go ingestion
or API, firmware, exposure from physical LAN/Internet clients, IPv6, Docker daemon
direct-routing policy, production PKI, revocation, load, or
RF/HIL/timing. End-to-end MQTT → Go → PostgreSQL → API, QoS1 deduplication and
backlog/reconnect scenarios remain unimplemented.
