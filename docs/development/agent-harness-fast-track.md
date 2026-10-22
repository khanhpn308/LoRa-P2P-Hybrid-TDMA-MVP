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

Expected last two statuses: `PLAN_ONLY`. The provider command builder now injects HTTP_PROXY, HTTPS_PROXY, http_proxy and https_proxy pointing to `http://lora-egress-proxy:3128`, with empty NO_PROXY/no_proxy. Docker network inspection now rejects `Internal=false`; this alone is not an external egress-policy attestation.

## Live-gating blockers — do not skip

1. Replace staging `example.com` with an approved **minimal** list of provider authentication and model endpoints, based on observed documentation and actual denied requests. Do not allow `*.google.com`, `*.openai.com`, private IPs, all CONNECT hosts, direct DNS escapes or privileged local access by default. Squid SNI/CONNECT host matching does not prove DNS rebinding resistance; control resolved destination IPs and host routes externally.
2. Authenticate by an officially supported method inside *dedicated* provider volumes only. Never copy WSL2 credentials, browser cookies, tokens or GitHub PAT into images/source. Confirm no passwords/API tokens leak into logs. API-key usage may incur separate charges from consumer subscriptions.
3. User/host administrator must independently verify actual Squid allow/deny logging and outbound filtering, owner of image IDs, isolated Docker resources, process/timeout quotas and auth profile permissions before enabling `--execute --confirm-external-egress-policy`. This flag is an acknowledgement, not security attestation.
4. For automated third-party AGY auditing, follow provider terms: consumer AGY CLI headless is for direct scripting/CI and is **not supported** as an embedded third-party agent or multi-account rotation. Prefer a legitimate Gemini API or Enterprise arrangement for a Python harness Auditor. AGY CLI is suitable only for the supported direct CLI/CI use cases.
5. Actual Worker issue editing, host ESP-IDF v6.1 builds, AGY/Gemini audited snapshot, signed commit-bound evidence and Draft PR publishing are a separate P1-B2-C milestone; none is complete by smoke testing.

References: https://www.antigravity.google/docs/faq/ ; https://www.antigravity.google/docs/cli/headless/ ; https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex
