# P1-B2 — Fast-track WSL2 readiness and live pilot

**Issue #34. State: DRAFT / Host static gates only. No real Codex/AGY request was run by CI.** ESP-IDF baseline remains v6.1.

## Existing operator-verified evidence (October 2026)

- Codex CLI Docker image 0.163.0 starts as UID 10001.
- AGY CLI Docker image 1.4.5 starts as UID 10001; the local WSL2 CLI version may differ.
- Both dedicated named Docker auth volumes are writable by UID 10001, but authentication is NOT_VERIFIED.
- `lora-agent-egress-staging` has `Internal=true`, IPv6 disabled and no direct route to `1.1.1.1:443` in one observed test.
- Squid `lora-egress-proxy` is the only member of `lora-agent-uplink-staging`; `example.com:443` CONNECT returned 200, `example.org` returned 403, five private/metadata addresses and both gateway IPs returned 403; ACL logging checked under user `proxy`.
- This is STAGING_ALLOWLIST_FUNCTIONAL_PASS only; external egress/host/DNS rebinding/production policy is NOT_VERIFIED.

## Quick preflight — no account calls

Run in clean P1-B2-B worktree with this PR checked out; no keys or secrets in command history:

~~~bash
set -e
python3 -m unittest discover -s tests/agent_harness -v
docker network inspect lora-agent-egress-staging --format 'Driver={{.Driver}} Internal={{.Internal}} IPv6={{.EnableIPv6}}'
docker inspect lora-egress-proxy --format 'Squid={{.State.Status}}'
CODEX_IMAGE=$(docker image inspect lora-codex-cli:0.163.0 --format '{{.Id}}')
AGY_IMAGE=$(docker image inspect lora-agy-cli:pilot --format '{{.Id}}')
python3 scripts/agent_harness/p1/provider_probe.py --provider codex --image-id "$CODEX_IMAGE" --network lora-agent-egress-staging --profile-volume lora-agent-codex-auth-pilot
python3 scripts/agent_harness/p1/provider_probe.py --provider agy --image-id "$AGY_IMAGE" --network lora-agent-egress-staging --profile-volume lora-agent-agy-auth-pilot
~~~

Expected last two statuses: `PLAN_ONLY`. The provider command builder now injects HTTP_PROXY, HTTPS_PROXY, http_proxy and https_proxy pointing to `http://lora-egress-proxy:3128`, with empty NO_PROXY/no_proxy. Codex smoke additionally sets `CODEX_HOME=/home/agent/.codex-clean-pilot` and `CODEX_CA_CERTIFICATE=/etc/ssl/certs/ca-certificates.crt` **before the image ID** and uses global `codex --ask-for-approval never exec` ordering. The user has shown `codex login status` SUCCESS from the same profile in `lora-codex-cli:0.163.0-ca-fixed`; runtime model call remains NOT_VERIFIED. Use inspected digest of the fixed image; do NOT use the old image tag. Docker network inspection now rejects `Internal=false`; this alone is not an external egress-policy attestation.

## Live-gating blockers — do not skip

1. Replace staging `example.com` with an approved **minimal** list of provider authentication and model endpoints, based on observed documentation and actual denied requests. Do not allow `*.google.com`, `*.openai.com`, private IPs, all CONNECT hosts, direct DNS escapes or privileged local access by default. Squid SNI/CONNECT host matching does not prove DNS rebinding resistance; control resolved destination IPs and host routes externally.
2. Authenticate by an officially supported method inside *dedicated* provider volumes only. Never copy WSL2 credentials, browser cookies, tokens or GitHub PAT into images/source. Confirm no passwords/API tokens leak into logs. API-key usage may incur separate charges from consumer subscriptions.
3. User/host administrator must independently verify actual Squid allow/deny logging and outbound filtering, owner of image IDs, isolated Docker resources, process/timeout quotas and auth profile permissions before enabling `--execute --confirm-external-egress-policy`. This flag is an acknowledgement, not security attestation.
4. For automated third-party AGY auditing, follow provider terms: consumer AGY CLI headless is for direct scripting/CI and is **not supported** as an embedded third-party agent or multi-account rotation. Prefer a legitimate Gemini API or Enterprise arrangement for a Python harness Auditor. AGY CLI is suitable only for the supported direct CLI/CI use cases.
5. Actual Worker issue editing, host ESP-IDF v6.1 builds, AGY/Gemini audited snapshot, signed commit-bound evidence and Draft PR publishing are a separate P1-B2-C milestone; none is complete by smoke testing.

References: https://www.antigravity.google/docs/faq/ ; https://www.antigravity.google/docs/cli/headless/ ; https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex

## Smoke blocked after successful Docker login

If `codex login status` reports `Logged in using ChatGPT` from `lora-codex-cli:0.163.0-ca-fixed` but the smoke returns `BLOCKED: Provider permission/authentication denial`, do not infer a failed subscription. The original message merged unrelated stderr signals, including sandbox setup denials. The live probe now prints `diagnostic.stderr_signals` and a hash/length only, never raw stderr, to discriminate `sandbox_backend`, `filesystem_permission`, `provider_auth`, `approval`, and `network_transport`. Review the flags, not secret-containing logs. Fail-closed behavior is unchanged.

Nested Codex Linux sandbox creation may require user namespace/mount operations denied by the deliberately hardened outer Docker runtime (`--cap-drop=ALL`, non-root, `no-new-privileges`). The outer container is **not** permission to remove isolation; do not use `--privileged`, mount `docker.sock`, or disable TLS verification. An outer-container-only sandbox proposal requires a separate security review before any smoke or coding task is changed. See https://github.com/openai/codex/issues/46246 and https://learn.chatgpt.com/docs/agent-approvals-security.

## Explicit Docker-only Codex smoke opt-in (security tradeoff)

Operator-provided live diagnostic (Oct 23, 2026): `exit_code=0`, `stdout_exact_expected_marker=true`, with `stderr_signals=[sandbox_backend, filesystem_permission]`. This is **not** a PASS: tools may fail silently when Codex attempts nested Linux sandbox inside the restricted Docker boundary. Reference: https://learn.chatgpt.com/docs/agent-approvals-security and https://github.com/openai/codex/issues/46246.

The default remains `codex exec --sandbox read-only` and fail-closed. For a **read-only disposable smoke fixture only**, the operator may explicitly elect to use Docker as the **sole filesystem/process sandbox** via `--accept-docker-only-isolation` (requires `--execute --confirm-external-egress-policy`). This selects **inner Codex** `--sandbox danger-full-access`; it does NOT add Docker `--privileged`, host mounts, Docker socket, writable repo, capabilities, or unrestricted Internet egress. It does permit a model-triggered command to access anything readable inside the container, including the mounted provider auth volume, so the host admin MUST approve this tradeoff and keep that volume dedicated. This is not production approval for unattended arbitrary worker code.

~~~bash
cd ~/projects/iot/LoRa-P2P-Harness-Proxy
git pull --ff-only
python3 -m unittest discover -s tests/agent_harness -q
CODEX_IMAGE=$(docker image inspect lora-codex-cli:0.163.0-ca-fixed --format '{{.Id}}')
python3 scripts/agent_harness/p1/provider_probe.py \
  --provider codex \
  --image-id "$CODEX_IMAGE" \
  --network lora-agent-egress-staging \
  --profile-volume lora-agent-codex-auth-pilot \
  --execute --confirm-external-egress-policy \
  --accept-docker-only-isolation --timeout 180
~~~

Success requires `READ_ONLY_MODEL_PROBE_PASS_ONLY`, exact stdout marker, exit 0 and no denial signals. The receipt records `sandbox_boundary=docker_outer_only`. Failure remains BLOCKED; do not sanitize failures into PASS. This smoke does not exercise a coding tool and cannot verify Worker/Repair/HIL behavior.
