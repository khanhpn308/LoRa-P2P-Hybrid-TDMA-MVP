# Issue #16 execution receipt, PR #87 security remediation

Remediation base: `2e3399c67517eac43acd478dae6c697f24f37246`.
PR base: `6b49ba090589496553de444b747b5b1d090a7650`.
Branch: `feat/16-local-infra`. PR remains Draft, no merge authorized.
This receipt replaces the earlier run, whose logs remain in Git history.

## Security findings addressed

- Client containers mount only the public CA and their own certificate/key as
  individual read-only files. Anonymous clients see only the public CA. Host
  client keys are mode 0600. Runtime visibility checks cover every identity;
  a fast unit regression checks the exact source/destination mount boundaries.
- TLS image copies only non-secret ACL/config from an allowlisted build context.
  Broker runs as uid/gid 1883; ACL owner is 1883:1883 with mode 0600. Dev broker
  also runs non-root. Startup log assertions check both brokers for ownership,
  read-only chown and other warnings. Broker key mount contains only the public
  CA, server certificate and server key, with group 1883 and mode 0640 access.
- A client on the separate default Docker bridge first reaches a temporary
  control listener bound to the host non-loopback IPv4. It then must fail on
  all three published service ports at that address. Localhost connections must
  succeed. No usable host address or failed control connection fails the test.

## Pre-edit report

```yaml
ISSUE_URL: https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/16
BASE_SHA: 2e3399c67517eac43acd478dae6c697f24f37246
BRANCH: feat/16-local-infra
ISSUE_ALLOWED_PATHS: [deploy/, scripts/verify_no_secrets.py, .env.example, tests/integration/]
APPLICABLE_RULE_IDS: N/A, infrastructure only; SEC-002 and ADR-0002 consulted
RULE_APPROVAL_STATUS: MQTT5 OWNER_ACCEPTED; MQTT contract DRAFT, cross-team review pending
CONTRACT_CONFLICTS: []
BLOCKED_DECISIONS: []
TEST_PLAN: [unit tests, full Docker integration smoke, runtime client mount visibility, non-root broker and ACL ownership/log checks, controlled non-loopback connection refusal, staged secret scan, allowlist/diff checks, fresh native review]
TASK_ROUTE: TOOLING_CI
START_DECISION: START_READY
STOP_REASON: NONE; explicit user security remediation request within Issue16 scope, preserve Draft PR87
CODEGRAPH: NOT_RUN; MCP unavailable and CLI not installed
WORKTREE: /home/khanh/projects/iot/LoRa-P2P-issue-16
```

## Versions and image identities

```text
$ docker version --format {{.Client.Version}} / {{.Server.Version}}
29.8.0 / 29.8.0
$ docker compose version
Docker Compose version v5.5.1
$ python3 --version
Python 3.12.3
$ openssl version
OpenSSL 3.0.13 30 Jan 2024 (Library: OpenSSL 3.0.13 30 Jan 2024)
$ ip -Version
ip utility, iproute2-6.1.0, libbpf 1.3.0
$ docker image inspect eclipse-mosquitto:2.0 postgres:16-alpine --format {{.RepoTags}} {{.Id}} {{.RepoDigests}}
[eclipse-mosquitto:2.0] sha256:212f89e1eaeb2c322d6441b64396e3346026674db8fa9c27beac293405c32b3c [eclipse-mosquitto@sha256:212f89e1eaeb2c322d6441b64396e3346026674db8fa9c27beac293405c32b3c]
[postgres:16-alpine] sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea [postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea]
$ docker inspect -f image_and_user <disposable TLS broker>
sha256:431d7b6b7f1d78cec51ae97bc327510bd5726a41550a5ef96a33cd90cd26d227 1883:1883
```

## Final execution

`python3 -m unittest discover -s tests/integration -v` exited 0. This executes
8 unit tests and the full Compose/Docker integration smoke, 9 tests total.
The test uses actual deployment configuration, changing only published port
numbers to random loopback ports in its disposable configuration. Database
health/persistence and all prior MQTT5 mTLS/ACL positive/negative tests still run.

```text
$ python3 -m unittest discover -s tests/integration -v
test_only_selected_identity_files_are_mounted_read_only (test_infra_security.ClientCredentialTests.test_only_selected_identity_files_are_mounted_read_only) ... ok
test_local_infrastructure (test_local_infra.LocalInfrastructureTest.test_local_infrastructure) ... PASS: Compose profiles, loopback-only bindings and dev network isolation
PASS: missing/empty PostgreSQL environment rejected
PASS: broker uid1883, ACL owner1883:1883 mode0600, server-only key mount; no ownership/startup warnings
PASS: each client sees only public CA and its own certificate/key; anonymous sees CA only
PASS: PostgreSQL healthcheck and persistence after container recreation
PASS: separate-network client reaches non-loopback control listener on 192.168.1.3
PASS: postgres reachable via localhost, rejected via non-loopback 192.168.1.3:44643
PASS: mqtt-dev reachable via localhost, rejected via non-loopback 192.168.1.3:44642
PASS: mqtt-tls reachable via localhost, rejected via non-loopback 192.168.1.3:44641
PASS: published TLS port verifies server CA and hostname
PASS: anonymous/no certificate rejected by TLS
PASS: untrusted certificate rejected by TLS
PASS: both Gateways and Backend exchange every allowlisted topic at MQTT5 QoS1
PASS: cross-Gateway writes, ClientID/username spoof, reversed roles, unknown CN and unlisted topic denied with PUBACK 135
PASS: cross-Gateway reads, wildcard leakage and Backend downlink reads deliver no messages
BROKER LOG BEGIN
mqtt-tls-1  | 1793082957: mosquitto version 2.0.22 starting
mqtt-tls-1  | 1793082957: Config loaded from /mosquitto/config/mosquitto.conf.
mqtt-tls-1  | 1793082957: Opening ipv4 listen socket on port 8883.
mqtt-tls-1  | 1793082957: mosquitto version 2.0.22 running
mqtt-tls-1  | 1793082989: Client connection from 172.23.0.1 failed: error:0A000126:SSL routines::unexpected eof while reading.
mqtt-tls-1  | 1793082992: New connection from 172.23.0.1:47386 on port 8883.
mqtt-tls-1  | 1793082992: OpenSSL Error[0]: error:0A000126:SSL routines::unexpected eof while reading
mqtt-tls-1  | 1793082992: Client <unknown> closed its connection.
mqtt-tls-1  | 1793082993: New connection from 172.23.0.4:38678 on port 8883.
mqtt-tls-1  | 1793082993: OpenSSL Error[0]: error:0A0000C7:SSL routines::peer did not return a certificate
mqtt-tls-1  | 1793082993: Client <unknown> disconnected: Protocol error.
mqtt-tls-1  | 1793082994: New connection from 172.23.0.4:38682 on port 8883.
mqtt-tls-1  | 1793082994: OpenSSL Error[0]: error:0A000086:SSL routines::certificate verify failed
mqtt-tls-1  | 1793082994: Client <unknown> disconnected: Protocol error.
mqtt-tls-1  | 1793082995: New connection from 172.23.0.4:38690 on port 8883.
mqtt-tls-1  | 1793082995: New client connected from 172.23.0.4:38690 as auto-53091175-B6E1-1CAB-653E-E163D85F7C62 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793082996: New connection from 172.23.0.5:41110 on port 8883.
mqtt-tls-1  | 1793082996: New client connected from 172.23.0.5:41110 as auto-B3FEC16F-D600-C333-6994-4BC7D9A3137B (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793082996: Client auto-B3FEC16F-D600-C333-6994-4BC7D9A3137B disconnected.
mqtt-tls-1  | 1793082996: Client auto-53091175-B6E1-1CAB-653E-E163D85F7C62 disconnected.
mqtt-tls-1  | 1793082997: New connection from 172.23.0.4:38702 on port 8883.
mqtt-tls-1  | 1793082997: New client connected from 172.23.0.4:38702 as auto-5DEED42B-01B4-9E40-1AB5-145CCB9D2B9E (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793082998: New connection from 172.23.0.5:41120 on port 8883.
mqtt-tls-1  | 1793082998: New client connected from 172.23.0.5:41120 as auto-FF697AB8-8555-117D-9235-86F104642181 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793082998: Client auto-FF697AB8-8555-117D-9235-86F104642181 disconnected.
mqtt-tls-1  | 1793082998: Client auto-5DEED42B-01B4-9E40-1AB5-145CCB9D2B9E disconnected.
mqtt-tls-1  | 1793082999: New connection from 172.23.0.4:35512 on port 8883.
mqtt-tls-1  | 1793082999: New client connected from 172.23.0.4:35512 as auto-2D4B5458-EEA8-038A-A367-70255DE89E16 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083000: New connection from 172.23.0.5:56748 on port 8883.
mqtt-tls-1  | 1793083000: New client connected from 172.23.0.5:56748 as auto-6EF917B2-DB05-6F33-7C1C-026A9DA38053 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083000: Client auto-6EF917B2-DB05-6F33-7C1C-026A9DA38053 disconnected.
mqtt-tls-1  | 1793083000: Client auto-2D4B5458-EEA8-038A-A367-70255DE89E16 disconnected.
mqtt-tls-1  | 1793083001: New connection from 172.23.0.4:35526 on port 8883.
mqtt-tls-1  | 1793083001: New client connected from 172.23.0.4:35526 as auto-5D861D06-E2E1-9AA2-33E0-50D1742F25E5 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083002: New connection from 172.23.0.5:56758 on port 8883.
mqtt-tls-1  | 1793083002: New client connected from 172.23.0.5:56758 as auto-6A00751D-147B-AEBF-D114-9AADA8473BA2 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083002: Client auto-6A00751D-147B-AEBF-D114-9AADA8473BA2 disconnected.
mqtt-tls-1  | 1793083002: Client auto-5D861D06-E2E1-9AA2-33E0-50D1742F25E5 disconnected.
mqtt-tls-1  | 1793083003: New connection from 172.23.0.4:35542 on port 8883.
mqtt-tls-1  | 1793083003: New client connected from 172.23.0.4:35542 as auto-61E7881F-D5B8-0B0D-5DF1-4D7EFA88F5CF (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083003: New connection from 172.23.0.5:56766 on port 8883.
mqtt-tls-1  | 1793083003: New client connected from 172.23.0.5:56766 as auto-DCB6AB0D-E36C-2C65-2BBB-34F000B1B5B3 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083003: Client auto-DCB6AB0D-E36C-2C65-2BBB-34F000B1B5B3 disconnected.
mqtt-tls-1  | 1793083003: Client auto-61E7881F-D5B8-0B0D-5DF1-4D7EFA88F5CF disconnected.
mqtt-tls-1  | 1793083005: New connection from 172.23.0.4:35546 on port 8883.
mqtt-tls-1  | 1793083005: New client connected from 172.23.0.4:35546 as auto-E23C75AE-6B86-BAF8-01D4-533D714D3A9D (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083005: New connection from 172.23.0.5:56774 on port 8883.
mqtt-tls-1  | 1793083005: New client connected from 172.23.0.5:56774 as auto-8D03A417-5402-31B1-A321-4D2D45B67CA5 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083005: Client auto-8D03A417-5402-31B1-A321-4D2D45B67CA5 disconnected.
mqtt-tls-1  | 1793083005: Client auto-E23C75AE-6B86-BAF8-01D4-533D714D3A9D disconnected.
mqtt-tls-1  | 1793083006: New connection from 172.23.0.4:35562 on port 8883.
mqtt-tls-1  | 1793083006: New client connected from 172.23.0.4:35562 as auto-A3F9DF7D-98EF-DF38-4F90-204DC52BC922 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083007: New connection from 172.23.0.5:56784 on port 8883.
mqtt-tls-1  | 1793083007: New client connected from 172.23.0.5:56784 as auto-589A1E81-C8B8-1B5A-EAAF-389C18223C40 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083007: Client auto-589A1E81-C8B8-1B5A-EAAF-389C18223C40 disconnected.
mqtt-tls-1  | 1793083007: Client auto-A3F9DF7D-98EF-DF38-4F90-204DC52BC922 disconnected.
mqtt-tls-1  | 1793083008: New connection from 172.23.0.4:40244 on port 8883.
mqtt-tls-1  | 1793083008: New client connected from 172.23.0.4:40244 as auto-C720FC43-3D16-7D1B-7BFE-A60040834ADA (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083009: New connection from 172.23.0.5:34896 on port 8883.
mqtt-tls-1  | 1793083009: New client connected from 172.23.0.5:34896 as auto-4CE05561-C67C-2FD6-B399-0668D8A21617 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083009: Client auto-4CE05561-C67C-2FD6-B399-0668D8A21617 disconnected.
mqtt-tls-1  | 1793083009: Client auto-C720FC43-3D16-7D1B-7BFE-A60040834ADA disconnected.
mqtt-tls-1  | 1793083010: New connection from 172.23.0.4:40254 on port 8883.
mqtt-tls-1  | 1793083010: New client connected from 172.23.0.4:40254 as auto-AE466FCD-BC3C-C770-BDBA-4D1792E55F2D (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083011: New connection from 172.23.0.5:34912 on port 8883.
mqtt-tls-1  | 1793083011: New client connected from 172.23.0.5:34912 as auto-6DBE9F11-FEAB-AD9B-76C8-0F2ECA6C5E02 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083011: Client auto-6DBE9F11-FEAB-AD9B-76C8-0F2ECA6C5E02 disconnected.
mqtt-tls-1  | 1793083011: Client auto-AE466FCD-BC3C-C770-BDBA-4D1792E55F2D disconnected.
mqtt-tls-1  | 1793083012: New connection from 172.23.0.4:40270 on port 8883.
mqtt-tls-1  | 1793083012: New client connected from 172.23.0.4:40270 as auto-0A48B94F-F3A1-4FF2-F72F-07D51BC719F9 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083013: New connection from 172.23.0.5:34918 on port 8883.
mqtt-tls-1  | 1793083013: New client connected from 172.23.0.5:34918 as auto-0EB00B2B-8508-2D37-DA12-4F22B765AA4E (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083013: Client auto-0EB00B2B-8508-2D37-DA12-4F22B765AA4E disconnected.
mqtt-tls-1  | 1793083013: Client auto-0A48B94F-F3A1-4FF2-F72F-07D51BC719F9 disconnected.
mqtt-tls-1  | 1793083014: New connection from 172.23.0.4:40272 on port 8883.
mqtt-tls-1  | 1793083014: New client connected from 172.23.0.4:40272 as auto-E2347082-7FD6-BEE8-6BDC-6626EB69897F (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083015: New connection from 172.23.0.5:34932 on port 8883.
mqtt-tls-1  | 1793083015: New client connected from 172.23.0.5:34932 as auto-3CB1D9CE-42BB-EC4C-8D15-577A79A236C3 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083015: Client auto-3CB1D9CE-42BB-EC4C-8D15-577A79A236C3 disconnected.
mqtt-tls-1  | 1793083015: Client auto-E2347082-7FD6-BEE8-6BDC-6626EB69897F disconnected.
mqtt-tls-1  | 1793083019: New connection from 172.23.0.4:37172 on port 8883.
mqtt-tls-1  | 1793083020: New client connected from 172.23.0.4:37172 as auto-0A921BDF-36B5-0FB0-B3C3-FB76632F5167 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083020: New connection from 172.23.0.5:39626 on port 8883.
mqtt-tls-1  | 1793083020: New client connected from 172.23.0.5:39626 as auto-FDF8D3A5-3EAA-AC59-7831-E64540D48197 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083020: Client auto-FDF8D3A5-3EAA-AC59-7831-E64540D48197 disconnected.
mqtt-tls-1  | 1793083020: Client auto-0A921BDF-36B5-0FB0-B3C3-FB76632F5167 disconnected.
mqtt-tls-1  | 1793083021: New connection from 172.23.0.4:37184 on port 8883.
mqtt-tls-1  | 1793083021: New client connected from 172.23.0.4:37184 as auto-0591337F-0657-96CC-3CFA-7F06B19BE0AA (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083022: New connection from 172.23.0.5:39638 on port 8883.
mqtt-tls-1  | 1793083022: New client connected from 172.23.0.5:39638 as auto-752E1802-A6A4-3380-2C66-5EF85904170D (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083022: Client auto-752E1802-A6A4-3380-2C66-5EF85904170D disconnected.
mqtt-tls-1  | 1793083022: Client auto-0591337F-0657-96CC-3CFA-7F06B19BE0AA disconnected.
mqtt-tls-1  | 1793083023: New connection from 172.23.0.4:37186 on port 8883.
mqtt-tls-1  | 1793083023: New client connected from 172.23.0.4:37186 as auto-46721AA5-C977-49C8-D765-1FF760B4B386 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083024: New connection from 172.23.0.5:39646 on port 8883.
mqtt-tls-1  | 1793083024: New client connected from 172.23.0.5:39646 as auto-0F275D9C-AEBC-1999-F674-92FD91D580F3 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083024: Client auto-0F275D9C-AEBC-1999-F674-92FD91D580F3 disconnected.
mqtt-tls-1  | 1793083024: Client auto-46721AA5-C977-49C8-D765-1FF760B4B386 disconnected.
mqtt-tls-1  | 1793083029: New connection from 172.23.0.4:44604 on port 8883.
mqtt-tls-1  | 1793083029: New client connected from 172.23.0.4:44604 as gw-b (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083029: Client gw-b disconnected.
mqtt-tls-1  | 1793083031: New connection from 172.23.0.4:44610 on port 8883.
mqtt-tls-1  | 1793083031: New client connected from 172.23.0.4:44610 as auto-9F59E110-3C56-3C78-D628-6692868977E2 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083031: Client auto-9F59E110-3C56-3C78-D628-6692868977E2 disconnected.
mqtt-tls-1  | 1793083032: New connection from 172.23.0.4:44622 on port 8883.
mqtt-tls-1  | 1793083032: New client connected from 172.23.0.4:44622 as auto-85A703A1-748E-0E81-10B0-615F092D80B1 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083032: Client auto-85A703A1-748E-0E81-10B0-615F092D80B1 disconnected.
mqtt-tls-1  | 1793083033: New connection from 172.23.0.4:44632 on port 8883.
mqtt-tls-1  | 1793083033: New client connected from 172.23.0.4:44632 as auto-8B5122A6-BF3D-1BA0-2883-50651183C502 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083034: Client auto-8B5122A6-BF3D-1BA0-2883-50651183C502 disconnected.
mqtt-tls-1  | 1793083035: New connection from 172.23.0.4:44644 on port 8883.
mqtt-tls-1  | 1793083035: New client connected from 172.23.0.4:44644 as auto-F589E3F6-E9FA-EC24-C5EF-B7D0262786F0 (p5, c1, k60, u'unknown').
mqtt-tls-1  | 1793083035: Client auto-F589E3F6-E9FA-EC24-C5EF-B7D0262786F0 disconnected.
mqtt-tls-1  | 1793083036: New connection from 172.23.0.4:44650 on port 8883.
mqtt-tls-1  | 1793083036: New client connected from 172.23.0.4:44650 as auto-51667386-EAC0-6E31-EF26-160DCD251149 (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083036: Client auto-51667386-EAC0-6E31-EF26-160DCD251149 disconnected.
mqtt-tls-1  | 1793083037: New connection from 172.23.0.4:44654 on port 8883.
mqtt-tls-1  | 1793083037: New client connected from 172.23.0.4:44654 as auto-6EA103E3-1908-7771-5D48-2F8C5C49D05B (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083039: New connection from 172.23.0.5:41634 on port 8883.
mqtt-tls-1  | 1793083039: New client connected from 172.23.0.5:41634 as auto-236A63FE-81E4-579D-97C8-40E526C5DCBF (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083039: Client auto-236A63FE-81E4-579D-97C8-40E526C5DCBF disconnected.
mqtt-tls-1  | 1793083045: Client auto-6EA103E3-1908-7771-5D48-2F8C5C49D05B disconnected.
mqtt-tls-1  | 1793083046: New connection from 172.23.0.4:38992 on port 8883.
mqtt-tls-1  | 1793083046: New client connected from 172.23.0.4:38992 as auto-3435DF9A-05C4-1F93-02E2-B8F62438D4C5 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083047: New connection from 172.23.0.5:41640 on port 8883.
mqtt-tls-1  | 1793083047: New client connected from 172.23.0.5:41640 as auto-5808C4E7-4AE5-C1F4-8717-DB396577019C (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083047: Client auto-5808C4E7-4AE5-C1F4-8717-DB396577019C disconnected.
mqtt-tls-1  | 1793083054: Client auto-3435DF9A-05C4-1F93-02E2-B8F62438D4C5 disconnected.
mqtt-tls-1  | 1793083056: New connection from 172.23.0.4:36556 on port 8883.
mqtt-tls-1  | 1793083056: New client connected from 172.23.0.4:36556 as auto-F7747658-FED9-97D1-31FC-89E6431E47AE (p5, c1, k60, u'gw-a').
mqtt-tls-1  | 1793083056: New connection from 172.23.0.5:53422 on port 8883.
mqtt-tls-1  | 1793083056: New client connected from 172.23.0.5:53422 as auto-7C175D30-8D4A-AAF3-8E0B-EF7506B49826 (p5, c1, k60, u'gw-b').
mqtt-tls-1  | 1793083056: Client auto-7C175D30-8D4A-AAF3-8E0B-EF7506B49826 disconnected.
mqtt-tls-1  | 1793083064: Client auto-F7747658-FED9-97D1-31FC-89E6431E47AE disconnected.
mqtt-tls-1  | 1793083065: New connection from 172.23.0.4:47676 on port 8883.
mqtt-tls-1  | 1793083065: New client connected from 172.23.0.4:47676 as auto-E1BD66BF-1F8D-DBC4-DEF2-D610F3732755 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083067: New connection from 172.23.0.5:53318 on port 8883.
mqtt-tls-1  | 1793083067: New client connected from 172.23.0.5:53318 as auto-8D8CC7C3-DF98-6748-74C7-23571212CB36 (p5, c1, k60, u'backend').
mqtt-tls-1  | 1793083067: Client auto-8D8CC7C3-DF98-6748-74C7-23571212CB36 disconnected.
mqtt-tls-1  | 1793083073: Client auto-E1BD66BF-1F8D-DBC4-DEF2-D610F3732755 disconnected.
BROKER LOG END
ok
test_forbidden_paths (test_verify_no_secrets.SecretScanTests.test_forbidden_paths) ... ok
test_ignored_untracked_secrets_not_read (test_verify_no_secrets.SecretScanTests.test_ignored_untracked_secrets_not_read) ... ok
test_private_key_under_innocent_name_in_index (test_verify_no_secrets.SecretScanTests.test_private_key_under_innocent_name_in_index) ... ok
test_public_cert_and_env_template_allowed (test_verify_no_secrets.SecretScanTests.test_public_cert_and_env_template_allowed) ... ok
test_schema_and_scanner_source_are_not_credentials (test_verify_no_secrets.SecretScanTests.test_schema_and_scanner_source_are_not_credentials) ... ok
test_symlink_rejected (test_verify_no_secrets.SecretScanTests.test_symlink_rejected) ... ok
test_unstaged_password_and_staged_diff (test_verify_no_secrets.SecretScanTests.test_unstaged_password_and_staged_diff) ... ok

----------------------------------------------------------------------
Ran 9 tests in 129.160s

OK
```

Secret scan after staging source changes, exit 0:

```text
$ python3 scripts/verify_no_secrets.py
PASS: tracked files, index and Git diff secret checks
```

`git diff --cached --check` passed. All changed paths are within Issue #16;
no symlinks were added. Scope, secret and whitespace checks were repeated after
staging this receipt. No test containers, volumes or files under the ignored
`tests/integration/secrets/` remain. The smoke removes its project image tag;
Docker may retain non-secret build cache. Expected TLS errors in the broker
log come from raw connection probes and deliberate authentication failures.
They are not ACL ownership warnings.

## Remaining Human Security Audit risks

- CA issuance, unique device CN binding, rotation, revocation and compromise
  recovery are not production implementations. Backend CN can publish downlinks
  across all Gateways and needs privileged issuance/key protection.
- Docker daemon access is privileged. A short-lived root helper changes only the
  group of the disposable server credential directory. It receives neither CA
  private key nor client keys. Host ownership remains for cleanup. This does
  not establish protection against a compromised host/daemon or image.
- Non-loopback evidence is IPv4 from a separate Docker bridge on this Linux
  host. Physical LAN/Internet clients, IPv6 and host firewall/direct-routing
  configurations still need independent deployment checks. Docker releases
  older than 28.0.0 have documented localhost exposure limitations.
- MQTT contract remains DRAFT pending Gateway/Backend/Infrastructure approval.
  Payload binding, schema/expiry/retain policy, session/queue limits, load and
  application integration remain separate responsibilities. Base image tags
  still float; exact tested digests are above and upgrades require review.
- Secret scanning is signature-based and checks tracked/index/diff content,
  not arbitrary secrets or full history. Abrupt process/daemon failure may
  require cleanup. Fresh native review uses the same model/shared filesystem;
  it is not an isolated Human Security Audit.

GitHub Actions: OWNER_WAIVED, not CI_PASS. CodeGraph: NOT_RUN, MCP/CLI unavailable.
Production security, integrated Go service and RF/HIL/timing: NOT_VERIFIED.
No RF transmission or hardware flash occurred.

References: [Mosquitto configuration](https://mosquitto.org/man/mosquitto-conf-5.html),
[Docker port publishing/direct-routing limits](https://docs.docker.com/engine/network/port-publishing/).

## Tested source hashes

All 12 source/doc hashes were recorded for the final run and verified unchanged
after it. This receipt is excluded from its own manifest.

```json
{
  ".env.example": "905025cf93021c830a3027a795848618b3a3e78e58ceae617c3fe074c677a325",
  "deploy/README.md": "7ee00a83cf9adf9fc7d943049a481dd6ff9f5029f5985dc73c5a3923e45bf903",
  "deploy/compose.yaml": "b3e54cbee81d894be1efeaf9503bab597d36c685bbe980668124051f18417a32",
  "deploy/mosquitto/.dockerignore": "7f76d511eef51d6698f19ac0aef710c62d0c54ba554b409fcbfcd205718e834f",
  "deploy/mosquitto/Dockerfile": "c2678f538f96a8276b74ccb773e75dab5adb0c2af30d05d37a9b76a52e9dbd72",
  "deploy/mosquitto/acl": "9004ac36132f6c2ba1b06e1941e7618da968fb4383d658734056fd2dbb111bf7",
  "deploy/mosquitto/tls.conf": "e6f38211afe260832d7fda66a7653d9112459b359e18bfd7ead329e158ea8fa0",
  "scripts/verify_no_secrets.py": "19c47465a0289d76716f62fdca3443f5a6be1cf1b3bf25185108568b6ae2812e",
  "tests/integration/README.md": "07fbc13f1c6f0f441719eab7e309ae1407f8d7781bada0754c077fca767d08a2",
  "tests/integration/test_infra_security.py": "04258e7688d2a56d26595c7f61947b36c280fd895ae2c920708d48fee19cb15b",
  "tests/integration/test_local_infra.py": "f84c991678370bb6488debf7f7c398de25e157f16f07fb5f10867ce292158c2c",
  "tests/integration/test_verify_no_secrets.py": "92931f2dcae40ba6c439d1940d4dabcc73f4f7041fe9aa609890341a81421ff2"
}
```
