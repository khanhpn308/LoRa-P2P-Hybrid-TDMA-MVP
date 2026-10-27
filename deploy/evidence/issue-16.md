# Issue #16 local execution receipt

Base: `6b49ba090589496553de444b747b5b1d090a7650`. Branch: `feat/16-local-infra`.
Native fast lane; Coordinator implemented the change. No signed MCP runner used.
Fresh native source review uses the same model and shared filesystem. It is not
an isolated security audit. Human Infrastructure/Security review and draft MQTT
cross-team approval remain required. GitHub Actions: OWNER_WAIVED, not CI_PASS.
RF/HIL/timing, remote exposure, production PKI and integrated Go service: NOT_VERIFIED.
CodeGraph: NOT_RUN, MCP/CLI unavailable.

## Pre-edit report

```yaml
ISSUE_URL: https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/16
BASE_SHA: 6b49ba090589496553de444b747b5b1d090a7650
BRANCH: feat/16-local-infra
ISSUE_ALLOWED_PATHS: [deploy/, scripts/verify_no_secrets.py, .env.example, tests/integration/]
APPLICABLE_RULE_IDS: N/A, infrastructure only; ADR-0002 and SEC-002 consulted
RULE_APPROVAL_STATUS: MQTT 5 OWNER_ACCEPTED; MQTT contract DRAFT, cross-team review pending
CONTRACT_CONFLICTS: []
BLOCKED_DECISIONS: []
TEST_PLAN: [secret scanner regression tests, Compose validation and env rejection, isolated PostgreSQL health and persistence, localhost dev binding, real Mosquitto MQTT5 mTLS and ACL positive and negative tests, diff and scope checks, fresh native review]
TASK_ROUTE: TOOLING_CI
START_DECISION: START_READY
STOP_REASON: NONE; owner-selected native fast lane, existing mTLS scheme and draft topic mapping used for local sample only; human security review required before acceptance
ISSUE_BODY_SHA256: 69a15036195ec5b6255f3392a203f290b80c19a97877079d3c853c045881f4f0
WORKTREE: /home/khanh/projects/iot/LoRa-P2P-issue-16
WORKER: Coordinator implementation fallback
CODEGRAPH: NOT_RUN, MCP unavailable and CLI not installed
```

## Tool versions and image identities

```text
$ docker version --format {{.Client.Version}} / {{.Server.Version}}
29.8.0 / 29.8.0
$ docker compose version
Docker Compose version v5.5.1
$ python3 --version
Python 3.12.3
$ openssl version
OpenSSL 3.0.13 30 Jan 2024 (Library: OpenSSL 3.0.13 30 Jan 2024)
$ docker image inspect eclipse-mosquitto:2.0 postgres:16-alpine --format {{.RepoTags}} {{.Id}} {{.RepoDigests}}
[eclipse-mosquitto:2.0] sha256:212f89e1eaeb2c322d6441b64396e3346026674db8fa9c27beac293405c32b3c [eclipse-mosquitto@sha256:212f89e1eaeb2c322d6441b64396e3346026674db8fa9c27beac293405c32b3c]
[postgres:16-alpine] sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea [postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea]
```

## Commands and results

Commands ran from the isolated Issue worktree. All commands below exited 0.
The smoke test resolved the actual deployment Compose file and changed only
published port numbers to random loopback ports in its disposable configuration.

```text
$ python3 -m unittest discover -s tests/integration -p test_verify_no_secrets.py -v
test_forbidden_paths (test_verify_no_secrets.SecretScanTests.test_forbidden_paths) ... ok
test_ignored_untracked_secrets_not_read (test_verify_no_secrets.SecretScanTests.test_ignored_untracked_secrets_not_read) ... ok
test_private_key_under_innocent_name_in_index (test_verify_no_secrets.SecretScanTests.test_private_key_under_innocent_name_in_index) ... ok
test_public_cert_and_env_template_allowed (test_verify_no_secrets.SecretScanTests.test_public_cert_and_env_template_allowed) ... ok
test_schema_and_scanner_source_are_not_credentials (test_verify_no_secrets.SecretScanTests.test_schema_and_scanner_source_are_not_credentials) ... ok
test_symlink_rejected (test_verify_no_secrets.SecretScanTests.test_symlink_rejected) ... ok
test_unstaged_password_and_staged_diff (test_verify_no_secrets.SecretScanTests.test_unstaged_password_and_staged_diff) ... ok

----------------------------------------------------------------------
Ran 7 tests in 0.725s

OK
$ python3 scripts/verify_no_secrets.py
PASS: tracked files, index and Git diff secret checks
$ git diff --cached --check
PASS, no output
$ python3 -u tests/integration/test_local_infra.py
PASS: Compose profiles, loopback-only bindings and dev network isolation
PASS: missing/empty PostgreSQL environment rejected
PASS: PostgreSQL healthcheck and persistence after container recreation
PASS: localhost dev broker reachable on published loopback port
PASS: published TLS port verifies server CA and hostname
PASS: anonymous/no certificate rejected by TLS
PASS: untrusted certificate rejected by TLS
PASS: both Gateways and Backend exchange every allowlisted topic at MQTT5 QoS1
PASS: cross-Gateway writes, ClientID/username spoof, reversed roles, unknown CN and unlisted topic denied with PUBACK 135
PASS: cross-Gateway reads, wildcard leakage and Backend downlink reads deliver no messages
BROKER LOG BEGIN
mqtt-tls-1  | chown: /mosquitto/config/mosquitto.conf: Read-only file system
mqtt-tls-1  | chown: /mosquitto/config/acl: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/wrong.crt: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/gw-b.key: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/backend.crt: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/wrong.key: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/gw-b.crt: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/server.key: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/server.crt: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/unknown.crt: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/ca.srl: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/gw-a.key: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/backend.key: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/unknown.key: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/gw-a.crt: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs/ca.crt: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs: Read-only file system
mqtt-tls-1  | chown: /mosquitto/certs: Read-only file system
mqtt-tls-1  | 1793079292: mosquitto version 2.0.22 starting
mqtt-tls-1  | 1793079292: Config loaded from /mosquitto/config/mosquitto.conf.
mqtt-tls-1  | 1793079292: Warning: File /mosquitto/config/acl has world readable permissions. Future versions will refuse to load this file.
mqtt-tls-1  | To fix this, use `chmod 0700 /mosquitto/config/acl`.
mqtt-tls-1  | 1793079292: Warning: File /mosquitto/config/acl owner is not mosquitto. Future versions will refuse to load this file.To fix this, use `chown mosquitto /mosquitto/config/acl`.
mqtt-tls-1  | 1793079292: Warning: File /mosquitto/config/acl group is not mosquitto. Future versions will refuse to load this file.
mqtt-tls-1  | 1793079292: Opening ipv4 listen socket on port 8883.
mqtt-tls-1  | 1793079292: mosquitto version 2.0.22 running
mqtt-tls-1  | 1793079315: New connection from 172.23.0.1:46618 on port 8883.
mqtt-tls-1  | 1793079315: OpenSSL Error[0]: error:0A000126:SSL routines::unexpected eof while reading
mqtt-tls-1  | 1793079315: Client <unknown> closed its connection.
mqtt-tls-1  | 1793079316: New connection from 172.23.0.4:33744 on port 8883.
mqtt-tls-1  | 1793079316: OpenSSL Error[0]: error:0A0000C7:SSL routines::peer did not return a certificate
mqtt-tls-1  | 1793079316: Client <unknown> disconnected: Protocol error.
mqtt-tls-1  | 1793079317: New connection from 172.23.0.4:33746 on port 8883.
mqtt-tls-1  | 1793079317: OpenSSL Error[0]: error:0A000086:SSL routines::certificate verify failed
mqtt-tls-1  | 1793079317: Client <unknown> disconnected: Protocol error.
mqtt-tls-1  | 1793079318: New connection from 172.23.0.4:58384 on port 8883.
mqtt-tls-1  | 1793079318: New client connected from 172.23.0.4:58384 as auto-82BEBCCB-23CD-3341-6785-1F6A27FDE000 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079319: New connection from 172.23.0.5:35920 on port 8883.
mqtt-tls-1  | 1793079319: New client connected from 172.23.0.5:35920 as auto-7DAAC0DA-3DBD-C66D-1D08-FEBA7F5755EE (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079319: Client auto-7DAAC0DA-3DBD-C66D-1D08-FEBA7F5755EE disconnected.
mqtt-tls-1  | 1793079319: Client auto-82BEBCCB-23CD-3341-6785-1F6A27FDE000 disconnected.
mqtt-tls-1  | 1793079320: New connection from 172.23.0.4:58400 on port 8883.
mqtt-tls-1  | 1793079320: New client connected from 172.23.0.4:58400 as auto-536E745F-F0F5-1A8F-362E-9D64A5EBA160 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079321: New connection from 172.23.0.5:35924 on port 8883.
mqtt-tls-1  | 1793079321: New client connected from 172.23.0.5:35924 as auto-98A6559F-9649-454B-AE4D-3ED2F5F7A3D3 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079321: Client auto-98A6559F-9649-454B-AE4D-3ED2F5F7A3D3 disconnected.
mqtt-tls-1  | 1793079321: Client auto-536E745F-F0F5-1A8F-362E-9D64A5EBA160 disconnected.
mqtt-tls-1  | 1793079322: New connection from 172.23.0.4:58410 on port 8883.
mqtt-tls-1  | 1793079322: New client connected from 172.23.0.4:58410 as auto-46055D24-18C8-EAB9-5499-9608A4DF0644 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079323: New connection from 172.23.0.5:35930 on port 8883.
mqtt-tls-1  | 1793079323: New client connected from 172.23.0.5:35930 as auto-593CC96B-E6D9-0987-06D4-80DA9F766FE0 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079323: Client auto-593CC96B-E6D9-0987-06D4-80DA9F766FE0 disconnected.
mqtt-tls-1  | 1793079323: Client auto-46055D24-18C8-EAB9-5499-9608A4DF0644 disconnected.
mqtt-tls-1  | 1793079325: New connection from 172.23.0.4:58426 on port 8883.
mqtt-tls-1  | 1793079325: New client connected from 172.23.0.4:58426 as auto-7C751E11-058C-C511-7125-E7A43DE6C57A (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079326: New connection from 172.23.0.5:35932 on port 8883.
mqtt-tls-1  | 1793079326: New client connected from 172.23.0.5:35932 as auto-D649FC3F-49F1-0CD5-D4DD-C7F128DEC727 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079326: Client auto-D649FC3F-49F1-0CD5-D4DD-C7F128DEC727 disconnected.
mqtt-tls-1  | 1793079326: Client auto-7C751E11-058C-C511-7125-E7A43DE6C57A disconnected.
mqtt-tls-1  | 1793079327: New connection from 172.23.0.4:58440 on port 8883.
mqtt-tls-1  | 1793079327: New client connected from 172.23.0.4:58440 as auto-6E4D8765-CB5E-4E74-A2D2-89DD51E3669B (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079328: New connection from 172.23.0.5:51734 on port 8883.
mqtt-tls-1  | 1793079328: New client connected from 172.23.0.5:51734 as auto-CD523419-BACE-7002-01C1-3906F3CAD7F4 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079328: Client auto-CD523419-BACE-7002-01C1-3906F3CAD7F4 disconnected.
mqtt-tls-1  | 1793079328: Client auto-6E4D8765-CB5E-4E74-A2D2-89DD51E3669B disconnected.
mqtt-tls-1  | 1793079329: New connection from 172.23.0.4:36222 on port 8883.
mqtt-tls-1  | 1793079329: New client connected from 172.23.0.4:36222 as auto-F1CE4F63-CA45-0323-0C2A-338F1CEDA277 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079330: New connection from 172.23.0.5:51746 on port 8883.
mqtt-tls-1  | 1793079330: New client connected from 172.23.0.5:51746 as auto-136166EB-8B2F-6D82-6861-01B64803FB8E (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079330: Client auto-136166EB-8B2F-6D82-6861-01B64803FB8E disconnected.
mqtt-tls-1  | 1793079330: Client auto-F1CE4F63-CA45-0323-0C2A-338F1CEDA277 disconnected.
mqtt-tls-1  | 1793079333: New connection from 172.23.0.4:36238 on port 8883.
mqtt-tls-1  | 1793079333: New client connected from 172.23.0.4:36238 as auto-94781B56-024F-FE6C-AF67-9DD5BF786748 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079334: New connection from 172.23.0.5:51758 on port 8883.
mqtt-tls-1  | 1793079334: New client connected from 172.23.0.5:51758 as auto-3BFDFB2C-D8B7-49B4-9314-2F0815A0FED5 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079334: Client auto-3BFDFB2C-D8B7-49B4-9314-2F0815A0FED5 disconnected.
mqtt-tls-1  | 1793079334: Client auto-94781B56-024F-FE6C-AF67-9DD5BF786748 disconnected.
mqtt-tls-1  | 1793079335: New connection from 172.23.0.4:36254 on port 8883.
mqtt-tls-1  | 1793079335: New client connected from 172.23.0.4:36254 as auto-68064476-6F7F-272D-EDD0-67AB43DE4D3B (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079336: New connection from 172.23.0.5:51760 on port 8883.
mqtt-tls-1  | 1793079336: New client connected from 172.23.0.5:51760 as auto-BE36C3DD-D51E-2A8D-D38F-FE84782C6620 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079336: Client auto-BE36C3DD-D51E-2A8D-D38F-FE84782C6620 disconnected.
mqtt-tls-1  | 1793079336: Client auto-68064476-6F7F-272D-EDD0-67AB43DE4D3B disconnected.
mqtt-tls-1  | 1793079337: New connection from 172.23.0.4:36258 on port 8883.
mqtt-tls-1  | 1793079337: New client connected from 172.23.0.4:36258 as auto-F5E0AF0C-7BA9-2A8E-ED31-66603AB1F890 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079338: New connection from 172.23.0.5:51764 on port 8883.
mqtt-tls-1  | 1793079338: New client connected from 172.23.0.5:51764 as auto-6335885A-D4B1-FD41-77E0-6487362997FD (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079338: Client auto-6335885A-D4B1-FD41-77E0-6487362997FD disconnected.
mqtt-tls-1  | 1793079338: Client auto-F5E0AF0C-7BA9-2A8E-ED31-66603AB1F890 disconnected.
mqtt-tls-1  | 1793079339: New connection from 172.23.0.4:51250 on port 8883.
mqtt-tls-1  | 1793079339: New client connected from 172.23.0.4:51250 as auto-0148CA73-F0DA-105E-C6E2-B55A8039F100 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079340: New connection from 172.23.0.5:51678 on port 8883.
mqtt-tls-1  | 1793079340: New client connected from 172.23.0.5:51678 as auto-06E43FF3-2412-2D32-BF49-D6073CF97CB9 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079340: Client auto-06E43FF3-2412-2D32-BF49-D6073CF97CB9 disconnected.
mqtt-tls-1  | 1793079340: Client auto-0148CA73-F0DA-105E-C6E2-B55A8039F100 disconnected.
mqtt-tls-1  | 1793079341: New connection from 172.23.0.4:51260 on port 8883.
mqtt-tls-1  | 1793079341: New client connected from 172.23.0.4:51260 as auto-2914C05D-9CA8-F4E2-65CA-5F02C3931455 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079342: New connection from 172.23.0.5:51680 on port 8883.
mqtt-tls-1  | 1793079342: New client connected from 172.23.0.5:51680 as auto-22A664F3-9D67-4F0C-BF83-F4D14535B34D (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079342: Client auto-22A664F3-9D67-4F0C-BF83-F4D14535B34D disconnected.
mqtt-tls-1  | 1793079342: Client auto-2914C05D-9CA8-F4E2-65CA-5F02C3931455 disconnected.
mqtt-tls-1  | 1793079343: New connection from 172.23.0.4:51270 on port 8883.
mqtt-tls-1  | 1793079343: New client connected from 172.23.0.4:51270 as auto-4E49BAA1-C792-0DC0-A668-9D1B58E90ACB (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079344: New connection from 172.23.0.5:51690 on port 8883.
mqtt-tls-1  | 1793079344: New client connected from 172.23.0.5:51690 as auto-B78BD959-3646-B074-2C41-3CA86C6B7CBC (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079344: Client auto-B78BD959-3646-B074-2C41-3CA86C6B7CBC disconnected.
mqtt-tls-1  | 1793079344: Client auto-4E49BAA1-C792-0DC0-A668-9D1B58E90ACB disconnected.
mqtt-tls-1  | 1793079345: New connection from 172.23.0.4:51284 on port 8883.
mqtt-tls-1  | 1793079345: New client connected from 172.23.0.4:51284 as auto-01F763D0-AF6A-B29D-765B-AA7FE976140F (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079348: New connection from 172.23.0.5:53210 on port 8883.
mqtt-tls-1  | 1793079348: New client connected from 172.23.0.5:53210 as auto-28C689E1-908F-6406-122F-201B15B26D3A (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079348: Client auto-28C689E1-908F-6406-122F-201B15B26D3A disconnected.
mqtt-tls-1  | 1793079348: Client auto-01F763D0-AF6A-B29D-765B-AA7FE976140F disconnected.
mqtt-tls-1  | 1793079350: New connection from 172.23.0.4:59824 on port 8883.
mqtt-tls-1  | 1793079350: New client connected from 172.23.0.4:59824 as auto-D56EFBDE-E644-8C32-ED3E-C496B8BA4B16 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079350: New connection from 172.23.0.5:53216 on port 8883.
mqtt-tls-1  | 1793079350: New client connected from 172.23.0.5:53216 as auto-49DCA4B9-BBAB-51BF-BA4B-A33F9B411777 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079350: Client auto-49DCA4B9-BBAB-51BF-BA4B-A33F9B411777 disconnected.
mqtt-tls-1  | 1793079350: Client auto-D56EFBDE-E644-8C32-ED3E-C496B8BA4B16 disconnected.
mqtt-tls-1  | 1793079351: New connection from 172.23.0.4:59840 on port 8883.
mqtt-tls-1  | 1793079351: New client connected from 172.23.0.4:59840 as gw-b (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079351: Client gw-b disconnected.
mqtt-tls-1  | 1793079353: New connection from 172.23.0.4:59850 on port 8883.
mqtt-tls-1  | 1793079353: New client connected from 172.23.0.4:59850 as auto-E4E5A332-053F-AE3C-9792-64AEBF73E772 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079353: Client auto-E4E5A332-053F-AE3C-9792-64AEBF73E772 disconnected.
mqtt-tls-1  | 1793079354: New connection from 172.23.0.4:59852 on port 8883.
mqtt-tls-1  | 1793079354: New client connected from 172.23.0.4:59852 as auto-F14EB84E-6E50-3412-2264-268D697BCA95 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079354: Client auto-F14EB84E-6E50-3412-2264-268D697BCA95 disconnected.
mqtt-tls-1  | 1793079355: New connection from 172.23.0.4:59864 on port 8883.
mqtt-tls-1  | 1793079355: New client connected from 172.23.0.4:59864 as auto-DFFA6C0E-C849-CC9F-5003-20CAC112CD90 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079355: Client auto-DFFA6C0E-C849-CC9F-5003-20CAC112CD90 disconnected.
mqtt-tls-1  | 1793079357: New connection from 172.23.0.4:59874 on port 8883.
mqtt-tls-1  | 1793079357: New client connected from 172.23.0.4:59874 as auto-D9C35D43-2101-70AF-8D61-34F18A9E9684 (p5, c1, k60, u'unknown').
mqtt-tls-1  | 1793079357: Client auto-D9C35D43-2101-70AF-8D61-34F18A9E9684 disconnected.
mqtt-tls-1  | 1793079358: New connection from 172.23.0.4:59882 on port 8883.
mqtt-tls-1  | 1793079358: New client connected from 172.23.0.4:59882 as auto-AFBD8E81-E246-F92D-3846-2D2E653BA05F (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079358: Client auto-AFBD8E81-E246-F92D-3846-2D2E653BA05F disconnected.
mqtt-tls-1  | 1793079359: New connection from 172.23.0.4:53892 on port 8883.
mqtt-tls-1  | 1793079359: New client connected from 172.23.0.4:53892 as auto-43ED8367-7893-BCBC-A9C3-6509D4A15184 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079360: New connection from 172.23.0.5:37886 on port 8883.
mqtt-tls-1  | 1793079360: New client connected from 172.23.0.5:37886 as auto-428F0741-477B-9BA2-B190-60C7B645FE4D (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079360: Client auto-428F0741-477B-9BA2-B190-60C7B645FE4D disconnected.
mqtt-tls-1  | 1793079367: Client auto-43ED8367-7893-BCBC-A9C3-6509D4A15184 disconnected.
mqtt-tls-1  | 1793079368: New connection from 172.23.0.4:51964 on port 8883.
mqtt-tls-1  | 1793079368: New client connected from 172.23.0.4:51964 as auto-A21936B3-00AE-2267-9E3F-D70B11467274 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079369: New connection from 172.23.0.5:51726 on port 8883.
mqtt-tls-1  | 1793079370: New client connected from 172.23.0.5:51726 as auto-B6D88CC9-D7A7-0131-759C-4BADA4819E35 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079370: Client auto-B6D88CC9-D7A7-0131-759C-4BADA4819E35 disconnected.
mqtt-tls-1  | 1793079376: Client auto-A21936B3-00AE-2267-9E3F-D70B11467274 disconnected.
mqtt-tls-1  | 1793079378: New connection from 172.23.0.4:51972 on port 8883.
mqtt-tls-1  | 1793079378: New client connected from 172.23.0.4:51972 as auto-957AEF14-E681-65DA-D69A-0566BB46A56C (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793079378: New connection from 172.23.0.5:41258 on port 8883.
mqtt-tls-1  | 1793079378: New client connected from 172.23.0.5:41258 as auto-64C68A42-D07B-B2ED-2823-E2277BA4BC59 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793079378: Client auto-64C68A42-D07B-B2ED-2823-E2277BA4BC59 disconnected.
mqtt-tls-1  | 1793079386: Client auto-957AEF14-E681-65DA-D69A-0566BB46A56C disconnected.
mqtt-tls-1  | 1793079388: New connection from 172.23.0.4:54250 on port 8883.
mqtt-tls-1  | 1793079388: New client connected from 172.23.0.4:54250 as auto-78C5616B-EADA-AEE3-8A77-6902D8CE3364 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079388: New connection from 172.23.0.5:51546 on port 8883.
mqtt-tls-1  | 1793079388: New client connected from 172.23.0.5:51546 as auto-89CDF519-FEC5-0B50-0615-18E87876405D (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793079388: Client auto-89CDF519-FEC5-0B50-0615-18E87876405D disconnected.
mqtt-tls-1  | 1793079396: Client auto-78C5616B-EADA-AEE3-8A77-6902D8CE3364 disconnected.
BROKER LOG END
.
----------------------------------------------------------------------
Ran 1 test in 113.840s

OK
```

The read-only mount ownership warnings above are emitted by the existing image.
They did not prevent startup or ACL enforcement. Image upgrades require review.
The test's generated Compose project was removed with `down -v`; no test
containers or private test keys remain. No RF transmission or flashing occurred.

## Tested source hashes

SHA256 hashes recorded for the final smoke run. This receipt is
excluded from its own manifest. All implementation files remained unchanged.

```json
{
  ".env.example": "905025cf93021c830a3027a795848618b3a3e78e58ceae617c3fe074c677a325",
  "deploy/README.md": "6a3e9b80fce4c11cd70a157f3a1c3e46de1da34a24d6000a12ece3099683564f",
  "deploy/compose.yaml": "784f2deeb8b49c41d7b940b1342487dfd795d99b4a273ec2032b2b2b07c18fe6",
  "deploy/mosquitto/acl": "9004ac36132f6c2ba1b06e1941e7618da968fb4383d658734056fd2dbb111bf7",
  "deploy/mosquitto/tls.conf": "e6f38211afe260832d7fda66a7653d9112459b359e18bfd7ead329e158ea8fa0",
  "scripts/verify_no_secrets.py": "19c47465a0289d76716f62fdca3443f5a6be1cf1b3bf25185108568b6ae2812e",
  "tests/integration/README.md": "0171ddd3fd4069978e37dd590972755a9e417204edeab019441f411427ba4df0",
  "tests/integration/test_local_infra.py": "5a3308f94c3ec9c9f1cb860949dd2b506780218f7eab3f7ee3f89980cd95afd1",
  "tests/integration/test_verify_no_secrets.py": "92931f2dcae40ba6c439d1940d4dabcc73f4f7041fe9aa609890341a81421ff2"
}
```
