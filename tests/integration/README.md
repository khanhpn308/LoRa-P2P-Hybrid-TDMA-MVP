# Local infrastructure integration tests

Run from the repository root:

```bash
python3 -m unittest discover -s tests/integration -p test_verify_no_secrets.py -v
python3 -u tests/integration/test_local_infra.py
```

Secret scanner tests use disposable Git repositories and synthetic markers.
The real infrastructure test requires Docker Engine, Compose, OpenSSL, Python 3
and the existing `postgres:16-alpine` and `eclipse-mosquitto:2.0` images. It starts
the deployment configuration with random localhost ports, a unique project,
temporary volumes, and one-day certificates under ignored
`tests/integration/secrets/`. Keys and resolved configuration never appear in
logs. An owner-only parent directory protects test material on the host;
readable files inside the Docker test mount let uid 1883 use them.

The test checks required environment validation, dev network separation,
loopback port bindings, PostgreSQL health/persistence across recreation, broker
hostname verification, MQTT 5 QoS1 flows for both Gateways and Backend, missing
and untrusted certificate rejection, and publish/read permissions. It includes
ClientID/username spoofing, unknown CNs, role reversal, unlisted topics and a
wildcard subscription. Unauthorized publishes must report MQTT 5 PUBACK reason
135. Mosquitto may accept unauthorized subscriptions while filtering delivery.
Those checks require a bounded receive timeout with no payload, after positive
delivery checks for the same topics. Payloads are transport probes, not schema
fixtures.

Output includes separate assertions and broker logs; a failed assertion exits
nonzero. Subprocesses and waits are bounded. Cleanup removes only the generated
project and volumes. Abrupt termination or a Docker daemon failure can require
manual cleanup using the project name printed in the broker logs.

These are local regression checks pending Human Security Audit. They do not
certify the draft MQTT contract, application semantics, integrated Go ingestion
or API, firmware, remote network exposure, production PKI, revocation, load, or
RF/HIL/timing. End-to-end MQTT → Go → PostgreSQL → API, QoS1 deduplication and
backlog/reconnect scenarios remain unimplemented.
