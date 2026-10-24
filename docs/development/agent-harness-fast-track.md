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

## Narrow Codex immutable-root warning exception

The Oct 23 operator run under explicit Docker-only isolation returned exit 0 and the exact `CODEX_SMOKE_OK` marker, but still had a filesystem-permission signal (541 bytes of stderr): **BLOCKED**. Earlier CLI output had the precise startup warning `WARNING: proceeding, even though we could not create PATH aliases: Read-only file system (os error 30)`. This warning is consistent with the immutable Docker rootfs; it is not evidence that a model-call tool failed.

For Codex ONLY, the evaluator can ignore exactly ONE entire occurrence of that known startup line and no other permission errors. It checks the remaining stderr for `permission denied`, `read-only file system`, `operation not permitted` or authorization failures. Different or repeated warnings remain fail-closed. The safe diagnostic now includes `benign_codex_alias_warning_count`. AGY handling and Docker sandbox limits are unchanged. Do not use this narrow exception to permit arbitrary filesystem writes or general autonomous coding.

## Oct 23: os error 13 during otherwise valid Codex response

Observed operator evidence: under `docker_outer_only`, the CLI returned exactly `CODEX_SMOKE_OK` with exit 0, but a **148-byte stderr line 2** contained `Permission denied (os error 13)`. No path alias, Codex home, session storage or workspace tags matched. The source operation/path remain `NOT_VERIFIED`; this is NOT sufficient grounds to whitelist this warning.

Codex's official non-interactive reference describes `codex exec --ephemeral` for invocations that **do not persist session rollout files**: https://learn.chatgpt.com/docs/non-interactive-mode. Since this command is a disposable read-only smoke, the provider adapter now always uses `exec --ephemeral`, regardless of which Codex isolation mode is selected. This avoids one class of background writes without relaxing filesystem ACLs or treating arbitrary os error 13 as benign.

Next operator action is a **single real smoke rerun** against the same pinned CA-fixed image and credential volume. The newly added ephemeral mode is not claimed to fix an unknown permission error until the run's `status` becomes `READ_ONLY_MODEL_PROBE_PASS_ONLY`. If blocked again, inspect the precise offending stderr line **locally**, redacting credentials and authorization URLs before reporting; do not weaken the validator based only on stderr keyword hashes. This change is smoke-specific and is not an authorization to disable persistence for production Worker recovery.

## Root cause: non-root Codex cannot traverse TemporaryDirectory

**New operator evidence (2026-10-23 07:34 +07):** Sanitized local stderr line 2: `ERROR codex_core::agents_md: error trying to find AGENTS.md docs: Permission denied (os error 13) environment_id="local"`. The same read-only Docker smoke returned exact `CODEX_SMOKE_OK` and exit code 0, but rightfully remained BLOCKED. This is an **AGENTS.md discovery filesystem access** error, not model authentication.

**Source-code root cause:** `provider_probe.py` creates a disposable WSL2 `tempfile.TemporaryDirectory()` (default private mode `0700`, owned by the WSL2 caller), and the container mounts it at `/workspace` while running as non-root `10001:10001`. Container UID 10001 cannot traverse the host-owned 0700 bind-mount root, causing EACCES during `AGENTS.md` ancestor discovery. The original implementation did not relax the disposable fixture directory. These facts make the diagnosis high-confidence; the post-fix live result is still `NOT_VERIFIED`.

**Fix:** only the newly created **harmless fixture** is made traversable `0755` and its sole `README.txt` readable `0644` before the Docker run. This does **not** chmod the monorepo, any real coding worktree, credentials volume, HOME, or arbitrary host files. `/workspace` remains a read-only bind mount; UID 10001, all capability/security flags, external egress confirmation and fail-closed permission validation are unchanged. One regression test checks the effective fixture mode **at the launch boundary**. Do not generalize this chmod to confidential snapshots or real candidate workspaces without a separate controlled ACL policy.

Rerun the existing documented `provider_probe.py` command once after `git pull --ff-only`. A local Docker read-only smoke PASS is established only by `READ_ONLY_MODEL_PROBE_PASS_ONLY` with no active permission/sandbox denial; CI unit PASS does not substitute for the live evidence.
