# PR #87 subscriber timeout remediation

Issue #16 authorizes `deploy/`, `scripts/verify_no_secrets.py`, `.env.example` and `tests/integration/`. This follow-up changes the integration harness, its regressions, documentation and evidence. ACL, broker configuration, MQTT topics and application contracts remain unchanged.

## Failure analysis

The acceptance run on `5d50edbf01583100a7ab183ca05e17110b7c8f68` ran 9 tests in 161.058 seconds and errored at `subscriber.communicate(timeout=10)`. The broker recorded the affected Gateway B connection at timestamp 1793097490 and its disconnect at 1793097498. The Python exception describes the local `docker run` process and its output pipe. It does not establish an MQTT authorization failure. The exact cause of Docker's delayed return was not measured.

The first development run separated Docker completion from MQTT but kept the old 8-second MQTT window. That run failed a positive exchange: Backend subscribed at 1793098779 and disconnected at 1793098787; the Gateway publisher connected at 1793098801. Publication happened after the receive window, so merely increasing the Docker completion timeout was insufficient. This failure is retained and superseded by the revised implementation.

## Bounded execution and unchanged authorization checks

The MQTT client now has a 45-second receive window. Negative publication must finish less than 37 seconds after starting the subscriber process. Because MQTT's timer starts after connection, this conservatively leaves at least 8 seconds after successful publication to observe delivery. Exceeding that budget fails, even if the subscriber subsequently exits 27. A regression simulates this race and rejects it.

Readiness remains bounded at 10 seconds. The existing publisher subprocess limit remains 90 seconds. Python separately waits at most 60 seconds for subscriber Docker completion after publication. A process timeout fails with an explicit NOT_VERIFIED authorization result and captured debug output. No timeout is accepted as an authorization success.

Every subscriber has a unique project-scoped container name. The finally path kills a lingering local Docker process, drains/reaps it with a 10-second bound, closes its pipe and attempts removal of that exact container with another 10-second bound. Removal errors fail except the expected already-removed container case. Removing the Popen context manager avoids its implicit unbounded exit wait after an earlier timeout. Abrupt daemon failure can still require manual cleanup.

Allowed exchanges still require SUBACK QoS 1, publisher PUBACK, subscriber exit 0 and the expected payload. Negative exchanges still require SUBACK, successful authorized publication, Mosquitto exit 27 and no payload. All four cross-Gateway, wildcard and Backend read-denial cases remain present. Each successful negative receive reports its identity/topic, MQTT result and elapsed Docker lifecycle. Both brokers' raw startup logs are retained.

## Regression evidence

The standalone unit command `python3 -m unittest -v test_infra_security test_verify_no_secrets`, run from `tests/integration/`, passed 18 tests in 8.025 seconds. These include the original scanner/mount checks and mocked process regressions. Mocked PASS output is captured inside the tests and is not mixed with actual runtime evidence.

Regressions cover delayed Docker completion, hung processes, missing SUBACK, publisher failure, positive delivery requirements, leaked negative payloads, unexpected MQTT/TLS/Docker exit codes, publication after the observation budget, container-removal errors/timeouts and local reap timeout. These unit tests do not substitute for actual Docker integration.

## Full development integration run

The inspected Host collector ran the complete integration discovery, including every actual Docker case and all unit regressions. Its direct exit code was 0. The suite ran **19 tests in 414.061 seconds, all PASS**, under an outer 600-second limit. All four negative receives completed with MQTT exit 27 and no payload. PostgreSQL health/persistence, both broker startup logs, mount isolation/modes, bridge-IPv4 network controls, server verification, both authentication failures, all 14 allowlisted exchanges and denied publishes also passed.

[Complete raw log](pr87-timeout/development-run.log), [runtime observations](pr87-timeout/development-observations.json), [execution command/exit](pr87-timeout/development-execution.json), [collector source](pr87-timeout/host-collector.py), [development fingerprint](pr87-timeout/development-fingerprint.json), [remediation patch](pr87-timeout/development-remediation.patch), [tested source hashes](pr87-timeout/tested-source-hashes.json) and [runtime image IDs](pr87-timeout/runtime-images.json) are retained. The [original negative timeout](pr87-timeout/previous-negative-timeout.log) and [first positive startup race](pr87-timeout/previous-positive-failure.log) remain visible as failed history.

The three modified source/document hashes matched after execution. The development patch uses zero context to avoid whitespace-only patch context in Git checks. The historical positive-failure log has CRLF normalized to LF; original and committed hashes are recorded in [artifact provenance](pr87-timeout/artifact-provenance.json). Generated containers, volumes and networks were absent after cleanup, and the ignored test secret directory was empty. No credentials were committed.


## Evidence binding and review limits

The attached development-run log and observations are from the staged worktree before this evidence was committed. `development-fingerprint.json`, `development-remediation.patch` and `tested-source-hashes.json` identify those exact tested bytes. They do not claim that the prior HEAD alone contains the remediation. The final committed HEAD is tested again, with a fresh complete candidate fingerprint and Host manifest outside the candidate. The PR body records those final results and hashes, plus the fresh Auditor verdict and post-audit comparison.

The Host collector only observes inspected assertions, Docker metadata, filenames and modes. It does not read key contents. Test keys and resolved secrets remain ignored and disposable. A receipt hash establishes byte consistency, not collector authentication. Fresh model review shares the model/provider and filesystem; it is not an isolated human security audit.

Human Infrastructure/Security review and Gateway/Backend MQTT approval remain pending. The contract remains DRAFT. Network evidence covers IPv4 from a separate Docker bridge to the Linux host, without physical LAN/Internet, IPv6, WSL2 or direct-routing certification. Production PKI, application payload binding, integrated Go/API and RF/HIL/timing remain NOT_VERIFIED. GitHub Actions is OWNER_WAIVED, with no CI_PASS claim. CodeGraph MCP/CLI was unavailable, NOT_RUN.

Sources: [Mosquitto subscriber options and exit codes](https://mosquitto.org/man/mosquitto_sub-1.html), [Python subprocess timeout and process management](https://docs.python.org/3.12/library/subprocess.html#subprocess.Popen.communicate).
