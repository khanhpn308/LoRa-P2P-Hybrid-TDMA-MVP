---
document_id: LORA-FW-PLAYBOOK-001
version: 0.1.0
status: PROPOSED
issue: 102
source_baseline: 34678739880f09af9f779358820d8b8c2ade0873
supported_module: ESP32-WROOM-32E
supported_radio: SX1276
supported_sdk: ESP-IDF v6.1
board_revision: NOT_VERIFIED_REQUIRES_TASK_INPUT
technical_review: PENDING_EMBEDDED_GATEWAY_NODE_RF_HARDWARE_SECURITY_QA_PROJECT_OWNER
runtime_router: NOT_IMPLEMENTED
upstream_skills: NOT_INSTALLED_OR_ACTIVATED
---

# ESP32 and SX1276 engineering playbook

<a id="task-index"></a>
## Task index

This is a proposed project workflow, with an audit of five upstream candidates. It adds no runtime routing or agent instructions. Read the Host-verified `AGENTS.md` first, then select the smallest relevant row. Load that workflow, its authority locators and the cited C Standard rows. The source inventory is for audit, not routine Worker context.

| Task or symptom | Proposed capability | Workflow | Initial evidence tier |
|---|---|---|---|
| SDK identity, configuration or build failure | `FW-IDF-001` | [Build and configuration](#fw-idf-001) | Host/build |
| Shared component, include or link failure | `FW-CMP-001` | [Component and CMake](#fw-cmp-001) | Host/build |
| Race, blocked task, ISR or timer handoff | `FW-RTOS-001` | [Concurrency](#fw-rtos-001) | Static, then unit/HIL as needed |
| Guru Meditation, watchdog, stack or core dump | `FW-DBG-001` | [Crash diagnosis](#fw-dbg-001) | Existing artifacts, then authorized HIL |
| Board identity, USB/UART, reset or brownout | `FW-HW-001` | [Board diagnosis](#fw-hw-001) | Host discovery, then authorized bench |
| SX1276 SPI, RxDone, FIFO or register mismatch | `FW-RAD-001` | [Radio diagnosis](#fw-rad-001) | Static/datasheet, then authorized HIL |
| Beacon loss, clock drift, ToA, guard or turnaround | `FW-TDMA-001` | [Timing diagnosis](#fw-tdma-001) | Static/simulation, then authorized HIL/RF |
| Ordinary documentation, no firmware behavior affected | None | [Manual selection](#selection-contract) | Document checks only |

Related sections: [authority](#authority), [capability mapping](#capability-mapping), [handoff design](#selection-contract), [negative cases](#selection-examples), [source audit](#source-audit), [file inventory](#file-inventory), [licensing](#licensing), [verification record](#verification-record).

<a id="authority"></a>
## Authority and applicability

The C Standard contains constraints; this playbook provides task procedures and evidence locators. [C Standard metadata and §0](C_CODING_STANDARD_V2.md#0-agent-entrypoint-execute-this-decision-flow), [§12](C_CODING_STANDARD_V2.md#12-blocked-decisions--never-resolve-in-coding-standard) and [§13](C_CODING_STANDARD_V2.md#13-deterministic-agent-checklist-required-pr-evidence) retain their actual status, `OWNER_APPROVED_PENDING_TECHNICAL_REVIEW / REVIEW_PROPOSAL_ONLY`. Its 104 existing Rule IDs are unchanged. Capability IDs below are proposed lookup keys, not new C Rule IDs or enforcement authority.

The supported architecture is C/FreeRTOS, ESP32-WROOM-32E and one SX1276 running Custom LoRa P2P MAC / Hybrid TDMA. Gateway executes the local radio schedule. The Go Backend plans future schedules over MQTT 5.0/TLS; it does not time RF slots. Arduino, PlatformIO, MicroPython, ESPHome, Zephyr, LoRaWAN, OTAA, adaptive-data-rate LoRaWAN procedures and ChirpStack are excluded. ESP32-S3/C3 examples do not establish WROOM-32E pins, flash/PSRAM configuration or native USB support.

The board revision, schematic, USB bridge, pin map, supply and fitted radio module are required task inputs for physical work. No specific PCB revision has been established by this document. `firmware/gateway_master/main/main.c` and `firmware/sensor_node/main/main.c` at the baseline are scaffolds. `firmware/components/{sx1276_driver,lora_mac,tdma_common,airtime_policy}/` contain README placeholders, with no implemented driver or timing test interface. Workflows describe how a future scoped task would investigate those features; they do not assert those features exist.

| Authority key | Exact source/revision and section | Status and use |
|---|---|---|
| `P-AGENTS` | [AGENTS.md](../../../AGENTS.md), baseline above; Git blob `0ca557b3d28db3c33c01dc1112ad65b1ee5f0647`; SHA-256 `aaa4a63bb551346fbd998f5cea868d97086d52b21fece21933f23fa4fafc8f89` | Execution scope and G0 entrypoint. A new task verifies its own current tracked bytes. |
| `P-C` | [C Standard](C_CODING_STANDARD_V2.md), baseline above, metadata/§0/affected rows/§12/§13 | Owner approved for technical review; enforcement activation pending. |
| `P-ADR` | [ADR-0001](../../adr/0001-hybrid-tdma.md), [ADR-0003](../../adr/0003-esp-idf-v6-1.md), baseline above; decision sections | ADR-0001 architecture direction accepted; its R1 rationale remains draft/pending technical review. ADR-0003 exact `v6.1` baseline approved by Owner. `firmware/esp-idf-version.txt` is the toolchain input. |
| `P-OPEN` | [Open decisions](../../../contracts/OPEN_DECISIONS.md), baseline above, D01–D13 and unlock conditions | Preserve each row's distinct status. D01/D11 security/wire and D03 RF permission remain blocked. No numeric profile is approved here. |
| `P-MAC` | [Radio MAC](../../../contracts/radio-mac/specification.md) §1/§3/§4; [TDMA schedule](../../../contracts/radio-mac/tdma-schedule.md) §1–§4, baseline above | `0.1.0-draft`, security/wire not frozen; P-10S-15 is a proposed simulator profile. Read for candidate behavior, not production authority. |
| `P-REQ` | [Requirements](../../requirements/requirements.md), baseline above, FW-001–FW-004, MAC/SEC/INT rows | DRAFT with R1 baseline and R2 remediation; G0 NOT_VERIFIED. Proposed coverage, not approval evidence. |
| `P-GATES` | [Acceptance gates](../../verification/acceptance-gates.md), [Native Fast Lane](../harness-fast-lane.md), [quality gates](../harness-quality-gates.md), baseline above | Evidence types and actual Host receipts remain separate. Fast Lane is instruction-based orchestration, not a hard isolation claim. |
| `V-IDF` | ESP-IDF annotated tag `v6.1` dereferenced to commit `fff9895c82d744c7237be8847347bdd1b07c6643` | Vendor API/build authority for ESP32. Version-matched pages and immutable source links appear below. No substitution with `latest`, prerelease or patch. |
| `V-SX` | [Local Semtech datasheet](../../Books/SX1276_Datasheet.pdf), baseline above, Rev. 7, May 2020, §4.1/§4.3/§6.4/§7.2 | Manufacturer reference for the fitted revision; hardware reviewer confirms applicability and errata. No generic register access authorizes RF. |
| `V-ESP` | [Local WROOM datasheet](../../Books/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf), baseline above, v2.1, §1.2/§3/§4/§6/§8/§9 | Module identification, pins, strapping, electrical and peripheral/reference-circuit lookup. Board schematic remains missing. |

Repository locators in this document refer to the exact source baseline in metadata, which includes merged PR #101. Recheck live Issue scope, source approval state and hardware revision at each task. The [system overview](../../architecture/system-overview.md) is R1 DRAFT and cannot supersede approved ADRs. A conflict, missing necessary authority or out-of-scope write is `STOP_AND_REPORT` under the existing entrypoint.

<a id="capability-mapping"></a>
## Capability mapping

Every row has the requested routing fields. Affected paths identify where to investigate, not authorization to change those paths. Rule references name existing rows within linked Standard sections; they remain review proposals. Inputs, procedures, evidence and stops link to the corresponding detailed workflow. A row's `PROPOSED` status applies even when its vendor API source is verified. Unsupported board, numeric or contract mappings are `NOT_VERIFIED`.

| CAPABILITY_ID | TASK_TRIGGER | AFFECTED_PATHS | PLAYBOOK_SECTION | EXISTING_C_RULE_IDS | AUTHORITY_SOURCE/REVISION | INPUTS | PROCEDURE | ACCEPTANCE_EVIDENCE | STOP_CONDITIONS | STATUS |
|---|---|---|---|---|---|---|---|---|---|---|
| `FW-IDF-001` | Build/config/SDK mismatch | `firmware/{gateway_master,sensor_node}/`, version file | [IDF](#fw-idf-001) | GOV-002/003/004; QA-001/002/005/006; [§1](C_CODING_STANDARD_V2.md#1-gov--agent-safety-scope-authority-all-firmware-work), [§11](C_CODING_STANDARD_V2.md#11-qa--evidence-testing-and-claim-discipline) | `P-ADR`, `V-IDF` build system | Exact SDK, disposable projects, scope | Version, config, first error, build | Command/exit, SDK and artifacts | Wrong SDK, generated-source mutation | PROPOSED |
| `FW-CMP-001` | Missing include/symbol/component | `firmware/components/**`, both application CMake files | [CMP](#fw-cmp-001) | C-004/006/019; ARCH-001/004/006/007; [§2](C_CODING_STANDARD_V2.md#2-c--formatting-names-types-and-interface-boundaries), [§6](C_CODING_STANDARD_V2.md#6-arch--component-and-dependency-ownership) | `P-ADR`, `V-IDF` component requirements | Real sources/headers and consumers | Trace public/private dependencies | Both consumer builds, API review | Placeholder mistaken for implementation | PROPOSED |
| `FW-RTOS-001` | Race, ISR, timer, timeout | `firmware/components/{sx1276_driver,lora_mac,tdma_common}/`, affected application tasks | [RTOS](#fw-rtos-001) | RTOS-001–010; MEM-001/005/006; ERR-001/002/005; [§3](C_CODING_STANDARD_V2.md#3-mem--bounded-resource-ownership-and-lifetime), [§4](C_CODING_STANDARD_V2.md#4-err--errors-diagnostics-recovery), [§5](C_CODING_STANDARD_V2.md#5-rtos--freertos-tasks-isr-and-timers) | `P-C`, `V-IDF` timer/FreeRTOS/SPI | Ownership, dispatch, limits, call paths | Trace handoff and lifecycle | Static paths, fault tests, separate HIL | Unknown dispatch/owner or timing budget | PROPOSED |
| `FW-DBG-001` | Panic, WDT, stack, core dump | Failing project and actual implicated component | [DBG](#fw-dbg-001) | MEM-003/004/007; ERR-003/007; RTOS-010; QA-001/003/005; [§3](C_CODING_STANDARD_V2.md#3-mem--bounded-resource-ownership-and-lifetime), [§4](C_CODING_STANDARD_V2.md#4-err--errors-diagnostics-recovery), [§5](C_CODING_STANDARD_V2.md#5-rtos--freertos-tasks-isr-and-timers), [§11](C_CODING_STANDARD_V2.md#11-qa--evidence-testing-and-claim-discipline) | `V-IDF` fatal errors/core dump/watchdogs; `U5` adapted classification | Exact-image ELF/map/config/log, capture format/tool | Decode, classify, inspect root cause | Matching artifact hashes, bounded repro | Mismatched ELF, unknown format/ciphertext, secret-bearing dump, missing config | PROPOSED |
| `FW-HW-001` | Board/USB/UART/power failure | Affected project config and approved board artifacts | [HW](#fw-hw-001) | GOV-004/008; RAD-007; QA-001/003/008; [§1](C_CODING_STANDARD_V2.md#1-gov--agent-safety-scope-authority-all-firmware-work), [§8](C_CODING_STANDARD_V2.md#8-rad--sx1276-radio-owner-phy-and-airtime), [§11](C_CODING_STANDARD_V2.md#11-qa--evidence-testing-and-claim-discipline) | `V-ESP`, exact PCB; `U4` adaptation | Schematic/revision, power, port owner | Host discovery before physical probes | USB evidence, boot log, rail trace | PCB/electrical identity missing; reset unsafe | PROPOSED; PCB NOT_VERIFIED |
| `FW-RAD-001` | RxDone/SPI/FIFO/register fault | `firmware/components/sx1276_driver/**`, affected radio owner | [RAD](#fw-rad-001) | RAD-001/002/003/004/005/007/009; RTOS-001/003/008; ERR-001/002/005; QA-001/003/008; [§8](C_CODING_STANDARD_V2.md#8-rad--sx1276-radio-owner-phy-and-airtime), [§5](C_CODING_STANDARD_V2.md#5-rtos--freertos-tasks-isr-and-timers), [§4](C_CODING_STANDARD_V2.md#4-err--errors-diagnostics-recovery), [§11](C_CODING_STANDARD_V2.md#11-qa--evidence-testing-and-claim-discipline) | `V-SX` §4.1/§4.3/§6.4; `V-IDF` SPI | Board/map, fitted revision, owner trace | Correlate IRQ, SPI and modem state | Register/waveform/event evidence | Missing driver/PCB/profile; unintended TX | PROPOSED; HIL NOT_VERIFIED |
| `FW-TDMA-001` | Beacon loss/drift/ToA/guard | `firmware/components/{tdma_common,airtime_policy,lora_mac}/`, both applications | [TDMA](#fw-tdma-001) | TDMA-001/002/005/006/007/008/009/010; RAD-006/008; ARCH-002/003; SEC-003/004; QA-002/003/008; [§10](C_CODING_STANDARD_V2.md#10-tdma--schedule-and-clock-behavior-no-numeric-freeze), [§8](C_CODING_STANDARD_V2.md#8-rad--sx1276-radio-owner-phy-and-airtime), [§6](C_CODING_STANDARD_V2.md#6-arch--component-and-dependency-ownership), [§7](C_CODING_STANDARD_V2.md#7-sec--parsing-secrets-replay-protocol-boundaries), [§11](C_CODING_STANDARD_V2.md#11-qa--evidence-testing-and-claim-discipline) | `P-MAC` §3/§4, `P-OPEN` D01–D05/D11, `V-SX` §4.1.1 | Reviewed profile/clock/security/model | Timeline, loss/recovery, measured budgets | Named simulation/HIL/RF artifacts | Unapproved auth/wire/TX/numeric bounds | PROPOSED; numeric mapping NOT_VERIFIED |

<a id="workflow-conventions"></a>
## Workflow conventions

All commands below are procedures for a future authorized task, not execution receipts for Issue #102. Use reviewed local tools only. Inputs such as `FW_REPO`, `FW_PROJECT`, `FW_BUILD`, `FW_ELF`, `FW_CORE_BASE64`, `FW_PORT`, `FW_BUILD_BUDGET` and `FW_TERMINATION_BUDGET` denote validated absolute paths, a confirmed device, a Host-selected run budget and a termination grace budget. `FW_CORE_BASE64` specifically names the verified UART Base64 body described in `FW-DBG-001`. They are not executable text copied from an Issue. Preserve direct exit codes and full sanitized logs outside the candidate. A timeout is incomplete evidence, not a successful test. Record the budget and termination/cleanup result; it is a run limit, not an RF or product deadline.

Build/config commands run in a disposable copy preserving `firmware/components/` and both sibling applications. Hardware access, resets, flashing and RF need their own scoped authorization and approved prerequisites. Opening a port can affect a running device. No workflow grants those actions merely because hardware is connected. Static inspection can continue while physical work is blocked. Follow [the evidence contract](#evidence-contract) for every result.

<a id="fw-idf-001"></a>
## FW-IDF-001: build and configuration

Prerequisites: exact current Issue allowlist, clean feature worktree, tracked version file, inspected project CMake/defaults and an already available v6.1 environment. Record SDK commit/container digest and `idf.py --version`; exact expected output is `ESP-IDF v6.1`. Wrong/missing tools stop the build path. Do not install a toolchain as a side effect of diagnosis.

1. Identify affected project roots. Both applications set `EXTRA_COMPONENT_DIRS "../components"`; preserve that relative layout in the disposable build copy. Review source/config hashes before building.
2. Inspect intentional defaults and the generated effective configuration separately. Confirm target `esp32`. A stored generated value can hide a changed default; compare old/new configuration rather than repeatedly cleaning. Menuconfig/reconfigure, if needed, operate only in the authorized disposable copy and their differences go to review.
3. Run the selected application build with a Host-chosen wall budget. Preserve the first compiler/configuration/link failure and referenced logs. If a shared component changes, build both consumers under `FW-CMP-001`.

```sh
idf.py --version
cat "${FW_REPO:?}/firmware/esp-idf-version.txt"
rg -n 'EXTRA_COMPONENT_DIRS|project\(' "${FW_PROJECT:?}/CMakeLists.txt"
rg -n 'CONFIG_IDF_TARGET|CONFIG_' "$FW_PROJECT/sdkconfig.defaults"
timeout --signal=INT --kill-after="${FW_TERMINATION_BUDGET:?}" "${FW_BUILD_BUDGET:?}" idf.py -C "$FW_PROJECT" -B "${FW_BUILD:?}" build
```

Checks and likely causes: SDK mismatch, wrong project root, configuration carrying stale selections, missing component registration or a real API migration error. Compare generated CMake/config artifacts with the selected inputs before changing code. Avoid `set-target`, `fullclean`, deleting lockfiles or hand-editing generated build files as speculative fixes. If defaults outside scope need changes, report the path and stop that mutation.

Expected evidence: full command/exit, source and SDK identity, selected project/target/config hashes, CMake/build logs, ELF/map/image digests when produced and explicit unbuilt consumers. No board is needed for a host build. `BUILD_VERIFIED` applies only to the built project and exact source.

Vendor locators: [v6.1 build system, project configuration/component discovery](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-guides/build-system.html), [immutable build-system source](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/docs/en/api-guides/build-system.rst). This procedure is independently authored from project/vendor authority. U1's unlicensed wording is not adopted.

<a id="fw-cmp-001"></a>
## FW-CMP-001: shared component and CMake diagnosis

Prerequisites: actual source/header paths, API consumers, owning component and exact v6.1 build graph. A README directory is not a component. At this baseline, implementing the placeholder modules requires a separately scoped firmware Issue.

1. Trace the missing header or symbol from the failing translation unit to its owning component. Use CodeGraph first when the repository is indexed and the tool exists; otherwise record `NOT_RUN` and use scoped `rg` plus manual caller review. Include callers outside the write allowlist as read-only evidence.
2. Check the real `idf_component_register` declaration, explicit sources/include paths and dependencies. Public-header dependencies belong to the public dependency surface; implementation-only dependencies belong to the private surface. Recheck exact SDK component names rather than copying an upstream `driver` dependency.
3. Preserve project layout and the single radio owner. Do not introduce registry dependencies, manifests, packaging, opaque wrappers or exported APIs just to solve a local link error. A new dependency needs its own compatibility/license review and authorized paths.
4. Build both Gateway and Node against the same shared source snapshot. Inspect the symbol/include resolution and any public-header/ABI change across consumers. An error in either consumer leaves integration incomplete.

```sh
rg -n 'EXTRA_COMPONENT_DIRS|idf_component_register|REQUIRES|PRIV_REQUIRES' "${FW_REPO:?}/firmware"
rg -n '#include|app_main' "$FW_REPO/firmware/gateway_master/main" "$FW_REPO/firmware/sensor_node/main"
# Repeat the bounded FW-IDF-001 build for each affected application.
```

Likely causes: no component CMake file, omitted source, incorrect include visibility, undeclared dependency, duplicate implementation or mismatch between a declaration and its definition. Stop if the fix requires an unapproved API/contract change, creating an unscoped component or importing a package with unresolved provenance.

Expected evidence: inspected CMake locations, source/public-header ownership, caller list, both direct build exits, effective component graph and compatibility findings. Compile success does not establish peripheral operation.

Vendor locators: [v6.1 build system, component requirements and minimal component CMakeLists](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-guides/build-system.html#component-requirements), immutable `V-IDF` build-system source above. U2 remains `PENDING_LICENSE`; no upstream template or publishing workflow is imported.

<a id="fw-rtos-001"></a>
## FW-RTOS-001: race, ISR, timer and timeout investigation

Prerequisites: actual task/ISR/timer registration code, SDK/configuration, radio owner, queue capacities and reviewed timeout/recovery policy. Read applicable Standard rows instead of re-declaring ownership/resource rules here.

1. Make a narrow event trace: producer/context → queue/notification → consumer/owner → SPI/state transition → completion/recovery. Mark buffer ownership, creation/enable ordering, finite wait and overflow paths. Trace transitive and function-pointer calls manually where graph coverage ends.
2. Identify hardware ISR, `ESP_TIMER_TASK` and `ESP_TIMER_ISR` paths from registrations and effective Kconfig. Inspect v6.1 callback/yield APIs, not the function's name or `IRAM_ATTR` alone. SDK interrupt-dispatched timers use their own yield request mechanism; verify the actual callees and build placement.
3. Check both cores' shared access, lock order and shutdown with in-flight callbacks. Explain how late/duplicate events, queue full, SPI failure and timeout reach the owner. Inspect the corresponding error and allocation return paths.
4. In a separately authorized test task, exercise those failure paths through the existing unit/fault fixture. Record test collection and skipped cases. Then capture HIL latency/queue behavior under the reviewed load if the claim needs physical timing.

```sh
rg -n 'xTaskCreate|xQueue|xSemaphore|esp_timer_create|dispatch_method|ESP_TIMER_|isr|spi_device' "${FW_REPO:?}/firmware"
```

At this scaffold baseline that search finds no operational radio handoff. Record the missing implementation; do not invent test commands or task traces. For a real race, likely causes include concurrent modem state machines, wrong callback context, lost notification, queue saturation, stale callback context or lock-order inversion. Raising priority, queue size or WDT limits without evidence does not identify the cause.

Stop for unknown callback dispatch, missing owner/lifetime, unapproved priority/guard requirements or out-of-scope ISR changes. Expected evidence: caller/callee source locations, effective configuration, lock/lifetime/event table, actual fault-test logs, compiler/map review for memory placement and separate HIL traces. A static graph cannot prove IRAM safety or timing.

Vendor locators: [v6.1 esp_timer callback dispatch](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-reference/system/esp_timer.html#callback-dispatch-methods), [v6.1 FreeRTOS SMP/tasks](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-reference/system/freertos_idf.html), [immutable timer source](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/docs/en/api-reference/system/esp_timer.rst), [immutable FreeRTOS source](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/docs/en/api-reference/system/freertos_idf.rst). U3 is an overlap locator only, pending license; this is an independent project/vendor procedure.

<a id="fw-dbg-001"></a>
## FW-DBG-001: Guru Meditation, WDT, stack and core dump

Prerequisites: full sanitized panic/reset log, exact failing image identity, matching application ELF/map/source/config and preceding events. Obtain existing artifacts before proposing a live reproduction. Treat core dumps as potentially secret-bearing memory; store restricted artifacts and publish only reviewed diagnostic excerpts.

1. Separate compile, boot and runtime failures. Locate the reported PC/backtrace in the exact matching ELF; a plausible line decoded with another build is not evidence. Preserve both cores' context when present, first failure and every rerun.
2. Form an evidence-led hypothesis: invalid load/store → bounds/lifetime/ownership; corrupted call path → buffer/callback corruption; IWDT → interrupt/critical-section obstruction; TWDT → task liveness/yield/lock path; stack failure → measured call depth and resource use. These are branches to investigate, not one-to-one diagnoses.
3. Before offline decoding, record the capture method, encoding/container, encryption state, artifact hash and installed decoder version. ESP-IDF v6.1 generates ELF core dumps; UART Base64 describes the transport encoding. Match the separate application ELF used for symbols to the failed image. Select the tool/options for the actual saved format:

| Saved artifact | Required format qualification |
|---|---|
| UART Base64 body | Save only the body, excluding `CORE DUMP START`/`CORE DUMP END` markers and unrelated logs. The bounded `-c` example below applies to this verified input. |
| Extracted core-dump ELF | Confirm it is the dump, not the application ELF. Inspect the installed `esp-coredump` help and verify its ELF input option plus matching application-ELF selection before decoding. |
| Binary dump or raw partition capture | Establish whether it is a supported dump container or a partition image with additional bytes. Verify the installed tool's binary/container option and matching application-ELF selection; do not infer format from the filename. |
| Encrypted-flash capture | Ciphertext is not a decodable plaintext dump. The `idf.py` core-dump commands cannot directly read an encrypted core-dump partition. Obtaining a decrypted artifact through a reviewed device-side path needs separate authorization; then classify its actual format. |

Only after qualifying the UART Base64 body and confirming the installed v6.1 wrapper/help and archived build, use:

```sh
sha256sum "${FW_ELF:?}" "${FW_CORE_BASE64:?}"
idf.py coredump-info --help
timeout --signal=INT --kill-after="${FW_TERMINATION_BUDGET:?}" "${FW_BUILD_BUDGET:?}" idf.py -C "${FW_PROJECT:?}" -B "${FW_BUILD:?}" coredump-info -c "$FW_CORE_BASE64"
```

`FW_PROJECT`/`FW_BUILD` contain the archived build whose application ELF is `FW_ELF`. The [pinned v6.1 wrapper](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/tools/idf_py_actions/debug_ext.py#L105-L150) requests automatic format detection for `-c`; that does not verify capture provenance or compatibility with an arbitrary saved artifact. Unknown encoding/container, ciphertext or unverified tool/options stop decoding with `NOT_VERIFIED`; a missing decoder is `NOT_RUN`. No port is used for the qualified saved-file example. If capture was not configured, report `NOT_AVAILABLE`; adding `espcoredump`, changing partitions/config or reflashing needs a permitted change and data-impact review. The budget limits analysis time, not device response time.

4. For an authorized live capture, use the verified monitor/port workflow in `FW-HW-001`. Inspect faulting code and the last successful event before modifying stack sizes or watchdog configuration. Select the smallest diagnostic configuration in a disposable build; measure its effect and repeat acceptance on the intended release configuration.

Likely causes: use-after-free, out-of-bounds write, unchecked allocation, stack exhaustion, starvation, callback race or electrical reset. A double exception alone does not prove a particular overflow; a clean canary alone does not prove memory safety. Stop on wrong image identity, incomplete dump, unapproved instrumentation or a secret that cannot be safely isolated.

Expected evidence: capture/format/encryption record, decoder version/options, artifact hashes, reset/panic classification, decoded source locations, tested hypothesis, actual reproduction conditions and a regression at the failing boundary where authorized. Missing board logs remain `HIL_NOT_VERIFIED`.

Vendor locators: [v6.1 fatal errors, register dump/backtrace](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-guides/fatal-errors.html#register-dump-and-backtrace), [v6.1 watchdogs, tuning](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-reference/system/wdts.html), [v6.1 core dump, configurations/commands](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-guides/core_dump.html), immutable [fatal-errors](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/docs/en/api-guides/fatal-errors.rst), [watchdogs](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/docs/en/api-reference/system/wdts.rst), [core dump](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/docs/en/api-guides/core_dump.rst). U5's symptom-based diagnostic organization is adapted with attribution; its fixed stack sizes and project commands are rejected.

<a id="fw-hw-001"></a>
## FW-HW-001: board, USB/UART, reset and brownout

Prerequisites: exact board/module marking and revision, schematic, USB bridge/transport, port ownership, supply path, attached circuit and approved safe state. The WROOM module label alone does not establish PCB pin routing, flash size or PSRAM. A bridge USB descriptor does not prove target firmware identity.

1. Start with host-only discovery, without opening ports. Record host/USB identity and stable device path. Do not change user groups, detach a driver or terminate another user's port owner automatically.

```sh
command -v idf.py
lsusb
ls -l /dev/serial/by-id
```

These Linux commands enumerate host state. Missing `lsusb`, missing directory or a WSL forwarding gap is a diagnostic result, not a firmware failure. They do not identify the PCB electrically or enter a bootloader.

2. Compare board schematic and `V-ESP` module pins/strapping/electrical tables. Confirm UART voltage/reference/framing and bridge/reset wiring before any probe. For brownout, use an authorized instrument capture at the module rail correlated with reset/load activity. Distinguish cable/supply sag, regulator transient response, ground/reference fault and strapping/reset interaction before changing firmware.
3. A live monitor is a physical action. Confirm scope, image, port, RTS/DTR behavior and possible restart/RF side effects. With an existing matching build and a separately authorized safe bench, inspect `idf.py monitor --help`, confirm v6.1 supports `--no-reset`, then use a bounded capture:

```sh
idf.py monitor --help
timeout --signal=INT --kill-after="${FW_TERMINATION_BUDGET:?}" "${FW_BUILD_BUDGET:?}" idf.py -C "${FW_PROJECT:?}" -B "${FW_BUILD:?}" -p "${FW_PORT:?}" monitor --no-reset
```

`--no-reset` avoids the monitor's requested reset; it cannot guarantee that the bridge/OS leaves RTS/DTR unchanged. If port-open behavior remains unknown, use existing logs and stop live capture. No console input, flash hotkeys or reset hotkeys are part of this procedure. A capture ending at the budget is complete only for its recorded observation window, not a product PASS.

4. Compare log timestamps/reset reasons with instrument evidence. Test only the isolated hypothesis within the approved fixture plan. Disabling brownout, guessing GPIO, full flash erase or changing eFuses is not a diagnostic shortcut.

Expected evidence: board/schematic revision, non-secret USB/port identity, confirmed running image, reset/boot log, supply trace with instrument setup and a specific conclusion or unresolved hypothesis. Stop for missing hardware documents, electrical uncertainty, lost fixture ownership or unintended reset/TX.

Vendor locators: `V-ESP` §3/§4/§6/§8/§9; [v6.1 IDF Monitor keyboard/reset behavior](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-guides/tools/idf-monitor.html), [immutable monitor source](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/docs/en/api-guides/tools/idf-monitor.rst). Adapted U4 host-first physical fault isolation is narrowed to WROOM-32E/ESP-IDF and existing authorization; no U4 helper or template is imported.

<a id="fw-rad-001"></a>
## FW-RAD-001: SX1276 SPI, IRQ, FIFO and readback

Prerequisites: implemented reviewed driver/test interface, single owner call paths, approved schematic/GPIO, fitted SX1276 revision/errata, mode-specific register source and a safe no-unintended-TX fixture. At this baseline the driver is absent; static planning can proceed, physical diagnosis is `NOT_RUN`. An SPI transaction can change state even when described as a read, especially FIFO access; review each transaction's side effects first.

1. Correlate the reported fault with owner state and timestamped ISR→task events. Trace which caller reaches SPI and modem-state transitions; compare timeout, queue-full and late-event paths. Use `FW-RTOS-001` for context/IRAM uncertainty.

```sh
rg -n 'spi_device|RxDone|TxDone|RegIrq|RegFifo|DIO|radio_owner' "${FW_REPO:?}/firmware"
```

2. From `V-SX` §4.3 and §6.4, prepare a reviewer-approved readback list: chip/version identity, observed operating mode, DIO mapping, IRQ mask/flags and FIFO address/count lifecycle. Record addresses/masks from that exact datasheet and fitted revision in the task evidence. No unapproved RegVersion acceptance value is introduced here. Distinguish read-only status, FIFO-consuming reads and write-to-clear flags.
3. On the authorized bench, correlate CS/SCLK/MOSI/MISO and DIO edges with the owner event trace. Check transaction framing/mode, power/reset and DIO routing. For a reported RxDone, compare modem state, latched IRQ, event delivery, FIFO pointer/count and checked destination-buffer capacity before interpreting payload bytes.
4. Classify the first failed boundary: electrical SPI, stale/wrongly mapped IRQ, lost handoff, wrong modem mode, FIFO handling or parser rejection. Capture pre/post state before owner-mediated recovery. Reset/reconfiguration, FIFO clearing and any TX test need the already approved task procedure and budget.

Stop for absent driver, unknown board/revision, multiple owners, unresolved bus side effects, unapproved RF parameters or recovery that bypasses ownership. There is deliberately no generic hardware CLI command: the project has no reviewed register console at this baseline. Creating one is a separately scoped task.

Expected evidence: exact source/config and datasheet sections, owner/call paths, approved register list, logic-analyzer settings/raw captures, decoded transactions, IRQ/event timestamps, timeouts/drop counters and actual outcomes. Hardware/API checks are distinct from RF reception and legal compliance. CRC/status identity and `TxDone` do not prove authenticity or peer receipt.

Vendor locators: `V-SX` §4.1.2/§4.1.7/§4.3/§6.4/§7.2; [v6.1 SPI master transaction/thread-safety documentation](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-reference/peripherals/spi_master.html), [immutable SPI master source](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/docs/en/api-reference/peripherals/spi_master.rst). This is a project/vendor procedure, not an upstream SX1276 capability claim.

<a id="fw-tdma-001"></a>
## FW-TDMA-001: Beacon loss, synchronization and RF timing

Prerequisites: actual implementation or explicitly named simulator, versioned candidate/approved profile, authenticated mapping design, half-duplex timeline, oscillator assumptions and separately approved RF/legal policy for physical transmissions. D01/D11 prevent assuming production authentication/bytes; D03 blocks TX authority; D02/D04/D05 prevent treating example timing as proven. Missing inputs allow a gap report or a labeled candidate simulation, not a production guarantee.

1. Read `P-MAC` §3/§4 and TDMA schedule §1–§4 with their draft status. Enumerate Beacon, downlink, contention, DATA, ACK, JOIN, retries, mode turnaround and every guard across the whole superframe boundary. Include JOIN spill into the next Beacon and the single radio's unavailable intervals.
2. Keep UTC expiry, local monotonic deadlines and Beacon-derived slot phase distinct. Trace reset/jump/holdover handling and authenticated schedule epoch/version. Check that a late or missed announcement does not silently leave a Node using old slot ownership.
3. For a named simulator, use its actual reviewed interface and preserve version, seed, inputs and assumptions. Exercise Beacon loss, delayed/duplicate events, drift, version changes, reset during staging, busy radio and exhausted airtime. Report modeled outcomes and omitted physical effects. No simulator exists in this scaffold; no invented simulator command is supplied.

```sh
rg -n 'beacon|superframe|guard|airtime|turnaround|schedule|esp_timer' "${FW_REPO:?}/firmware"
rg -n '^\| D0[1-5]|^\| D11' "$FW_REPO/contracts/OPEN_DECISIONS.md"
```

4. For separately authorized HIL/RF, capture the same event timeline with calibrated clocks/instruments, actual payload lengths and complete PHY settings. Compare vendor ToA calculation with measured on-air duration. Build a budget from measured oscillator error, synchronization age, IRQ/task/SPI delay, turnaround, scheduling delay and measurement uncertainty. Its accounting and bounds need technical review; this playbook supplies no numeric guard formula or threshold.
5. Verify loss/recovery and safety behavior against the reviewed mapping/sync policy. Explicitly observe the suppressed-transmission path when assurance is inadequate. Correlate all emitted Beacon/ACK/retry/join/alert airtime with admission; priority is not an airtime exemption. A candidate count of three missed Beacons or a K+3 horizon is not a frozen requirement.

Likely causes: stale mapping, clock-domain confusion, unaccounted half-duplex window, model/PHY mismatch, queue/IRQ delay or unsafe holdover. Stop on missing auth/wire/RF approval, unknown profile, uncalibrated measurement or demand for a numeric guarantee from source review. Backend schedule publication cannot establish local slot timing.

Expected evidence: candidate/approved profile identity, model assumptions/results, full timeline, calibration, raw HIL traces, actual on-air measurements, uncertainty and reviewer disposition. `SIMULATION_VERIFIED`, `HIL_VERIFIED`, `RF_VERIFIED` and legal compliance each need their own evidence; none is inferred from another.

Sources: `P-OPEN`, `P-MAC`, `P-ADR`; `V-SX` §4.1.1, particularly LoRa time-on-air; `V-IDF` timer source above. The five skills provide no approved Custom MAC/TDMA profile. This workflow is independently authored from project/manufacturer authority.

<a id="selection-contract"></a>
## Coordinator, Worker and Auditor selection contract, design only

No machine-readable router, Host loader change or automatic context injection is implemented by this document. Task and affected-boundary classification is a reviewable manual heuristic, not proven deterministic selection. For a recorded selection, ordering/deduplication, Rule-ID existence and source/hash comparisons are mechanically checkable; report verification only when those checks actually ran. They do not prove the interpretive selection correct. Use the following manual procedure:

1. Coordinator reads the live OPEN Issue, exact allowed paths, acceptance criteria, current branch/base and affected read-only consumers. Distinguish paths actually affected from paths merely mentioned in background. A docs-only task selects no firmware capability unless its AC explicitly require evaluating a firmware workflow.
2. Match each concrete trigger/affected implementation boundary to the [task index](#task-index). Record the supporting Issue criterion/path/evidence and the reasoning for selected rows and relevant exclusions, then order selected rows by the index and remove duplicates. Build/config suggests IDF; shared CMake/public component suggests CMP and IDF when build evidence is required; a panic suggests DBG and adds RTOS/HW/RAD when evidence supports that boundary. Unresolved classification is `NOT_VERIFIED`; inspect the narrow source needed to decide. If scope or source authority remains ambiguous, `STOP_AND_REPORT` and record the responsible Owner/technical reviewer's required decision or approval before the dependent action. Selection rationale does not supply that approval.
3. Resolve the chosen rows into exact existing Rule IDs and authority sections. Include Standard metadata/§0/§12/§13, the chosen rows and needed source excerpts only. Expand a range such as RTOS-001–010 to the existing rows, preserving source revision and status. Add further existing rules only when the actual diff warrants them; never fabricate an ID. Missing mapping is `NOT_VERIFIED` and blocks dependent guidance.
4. Before Worker edits, a trusted Host runs `python3 scripts/agent_harness/agent_context.py --repo <candidate>`, checks `HOST_CONTEXT_LOADED`, tracked blob/source/bytes/SHA-256, and places the complete returned `agent_input` into the actual Worker request. Store the command/direct exit and exact receipt outside the candidate. Missing/dirty/symlinked/drifted AGENTS or unavailable Host gate is `BLOCKED`. A model's statement or a copied hash is not Host verification.
5. Assemble a bounded handoff with the Issue URL/body digest, AC, exact allowed paths, base/candidate identity, full verified AGENTS context, selected capability IDs/section excerpts and rationale, unresolved classifications/required approvals, expanded C Rule rows/status, source pins, necessary consumer paths, inputs, acceptance evidence and explicit unresolved decisions. Do not include all five SKILL.md files, all 104 rules, vendor manuals or the inventory by default. Missing required input stops only the dependent action; safe scoped inspection may continue.
6. Worker reports consulted/applied IDs, actual changes versus scope, conflicts/gaps, commands/exits and missing evidence. No self-reported selection or successful build promotes a design, security or physical gate.
7. Host runs applicable quality gates and collects its own command/log receipts. Preserve candidate fingerprint, full base-to-candidate patch/command/exit/hash, manifest and receipt hashes before a fresh read-only Auditor. Auditor receives the same exact AGENTS version/hash, AC, selected sources, frozen diff and Host evidence, then checks actual scope, source claims, false positives and evidence integrity. Native context separation does not prove filesystem/provider isolation.
8. Host reruns checks and compares candidate/diff/evidence fingerprints after review. Drift invalidates the review; fixes require new receipts and re-review. Missing receipts, unresolved P0/P1, authority conflicts or required human review block readiness. Delivery is a Conventional Commit and Draft PR, then human review; no automatic merge, flash, TX or policy activation.

Fallback when no router exists: execute steps 1–8 manually and record selected rows, rationale and unresolved decisions in the handoff. This provides reviewable reasoning and fixed ordering, not proof of deterministic task classification. If the playbook is unavailable or still unapproved, use verified AGENTS, current authority and applicable Standard review rows directly; mark capability guidance `NOT_VERIFIED`. Do not activate upstream skills to fill the gap. A future router/loader/test implementation needs another specifically scoped Issue.

<a id="selection-examples"></a>
## Selection and fail-closed examples

| Case | Manual selection and expected disposition |
|---|---|
| Ordinary README typo | Zero firmware capabilities; common scope/link/diff checks. No firmware build implied. |
| ESP-IDF build error in Gateway | `FW-IDF-001`; GOV-003 and QA-005 with exact v6.1 evidence. No board required. |
| Shared component include failure | `FW-CMP-001`, plus `FW-IDF-001` for both consuming builds; C-006 and ARCH-004. An absent implementation stays absent. |
| Guru Meditation with matching archived ELF | `FW-DBG-001`; MEM/ERR/QA rows in its mapping. Add RTOS only when task/ISR evidence points there. |
| SX1276 SPI RxDone fault | `FW-RAD-001` plus `FW-RTOS-001` for ISR/owner handoff; RAD-001–004/009, RTOS-001/003/008, ERR-001/002/005 and QA-001/003/008. Add HW if electrical/PCB facts are unresolved. |
| Suggestion to enable LoRaWAN/OTAA/ADR or ChirpStack | REJECT under GOV-005/ARCH-005. No related upstream instruction is activated. |
| Suggestion to run upstream `just <project>::build` or a bundled flash wrapper | REJECT command. Use inspected project roots and `FW-IDF-001`; no upstream script execution. |
| Compile PASS, missing HIL logs | `BUILD_VERIFIED` only for that build; `HIL_NOT_VERIFIED`, `RF_NOT_VERIFIED`, timing NOT_VERIFIED. |
| No Host-verified AGENTS context | `BLOCKED` before any Worker edit even if the model says it read AGENTS. |
| Legacy 8-byte header or fixed frequency/guard requested without technical approval | `STOP_AND_REPORT`, D01/D03/D04/D11 as applicable. No production codec, numeric freeze or TX. |
| U1/U2/U3 candidate lacks prose license | PENDING_LICENSE, no adaptation/import. Independent project/vendor procedure may be reviewed without adopting that content. |

<a id="evidence-contract"></a>
## Evidence and technical review

Each result binds Issue/base/head, source/config/toolchain and board/fixture identity where relevant, selected capabilities/C Rule IDs and approval states, command/direct exit, timestamp, expected/actual observation, artifact/hash and limitations. Build copies, simulator and DUT observations remain distinguishable. Sensitive memory/logs stay restricted; an artifact hash does not authenticate its collector.

| Evidence tier | Establishes within recorded conditions | Does not establish by itself |
|---|---|---|
| Host static/document checks | Scope, Rule-ID existence, links, source identity and inspected paths | Runtime ownership, electrical or radio behavior |
| Build/unit/contract | Named compiler/test cases on exact source and toolchain | Real ISR latency, on-air reception or contract approval |
| Simulation | The recorded model under its inputs/assumptions | Actual oscillator, interference, board or PHY behavior |
| HIL | Named DUT/config/fixture observations | RF/legal compliance or all field conditions |
| RF measurement | Measured on-air behavior with calibrated setup/profile | Authorization to transmit, regional conformity or security approval |
| Legal/RF approval | Recorded authorized reviewer decision for exact profile/jurisdiction | Firmware timing or test completion |

Required reviewers are Embedded Gateway and Node, RF/Hardware, Security/QA and Project Owner. Record actual reviewer, reviewed SHA, finding disposition and approval evidence. No signature or activation is supplied by this draft. Preserve D01–D13 states. C Standard review, playbook review, build/CI, model audit, human security review, HIL/RF/timing and G0–G6 have separate evidence. GitHub Actions `OWNER_WAIVED` is not CI PASS.

<a id="source-audit"></a>
## Five-source provenance and security audit

Audit date: 2026-10-28. Sources were read as data from no-checkout Git clones outside the candidate; no upstream script, validator, test, installer, template, flasher or agent configuration was executed or activated. This is a bounded static source review, not malware certification, dependency installation or legal sign-off. Git blob SHA identifies a Git object; SHA-256 below hashes exact file bytes. Repository commits are immutable provenance, not approval. URLs containing a branch in audited prose are navigation only, not adopted pins.

| Key/candidate | Repository and immutable commit | Exact SKILL.md, blob SHA and content SHA-256 | License/disposition |
|---|---|---|---|
| U1 `esp-idf` | `pedrominatel/awesome-esp-ai` @ `ed3956d8572f7d179a96887d66fbf089d1502720` | [skills/esp-idf/SKILL.md](https://github.com/pedrominatel/awesome-esp-ai/blob/ed3956d8572f7d179a96887d66fbf089d1502720/skills/esp-idf/SKILL.md); blob `38bd118e37adc2d25809a9efecadc9dade8145b3`; SHA-256 `16041d792367a20c0548a1aa440ecd42d7a242e80cf511b95515aa14163f9046` | No repository/skill prose license found in pinned tree. PENDING_LICENSE, no content adoption. |
| U2 `esp-idf-components` | Same immutable repository/commit as U1 | [skills/esp-idf-components/SKILL.md](https://github.com/pedrominatel/awesome-esp-ai/blob/ed3956d8572f7d179a96887d66fbf089d1502720/skills/esp-idf-components/SKILL.md); blob `b97c2d6ba0f8ecb9392f6ed2ecf6372427081204`; SHA-256 `a82676b30bbae66943d8e74f0784c99d7c982c4acf09da8307f6a5345bb958ed` | Template-local Apache-2.0 file does not establish SKILL/reference prose permission. PENDING_LICENSE, no template/prose import. |
| U3 `esp32-firmware-engineer` | `adamlipecz/esp32-firmware-engineer-skill` @ `2d5737faed742c09dfe89197871b635e7608376b` | [esp32-firmware-engineer/SKILL.md](https://github.com/adamlipecz/esp32-firmware-engineer-skill/blob/2d5737faed742c09dfe89197871b635e7608376b/esp32-firmware-engineer/SKILL.md); blob `13b82e4b4165d27b13548557a9a6fc2e7fe97e4f`; SHA-256 `547d2304125b95434e70d1456fd670f99e78417075ded04e825c4af081e67ac5` | No license file found in pinned tree. PENDING_LICENSE, no prose/script/template adoption. |
| U4 `esp32-development` | `magnus919/agent-skills` @ `f4950d8743b6590762b3227b8ba9ecc55b936855` | [esp32-development/SKILL.md](https://github.com/magnus919/agent-skills/blob/f4950d8743b6590762b3227b8ba9ecc55b936855/esp32-development/SKILL.md); blob `601de8623bfc69c45e11d472c78758ca89f8f151`; SHA-256 `19b53675b50873d093c0e016c63af6fff1f7b3f05d0d4f58ac54a8edbef6329c` | MIT, copyright 2026 Magnus Hedemark, pinned root LICENSE.md. ADAPT limited workflow ideas, attribution below. No helper/template copied. |
| U5 `esp32-debugging` | `laurigates/mcu-tinkering-lab` @ `34437ae5875057d4d407886ab3c9b8f84f6ea523` | [.claude/skills/esp32-debugging/SKILL.md](https://github.com/laurigates/mcu-tinkering-lab/blob/34437ae5875057d4d407886ab3c9b8f84f6ea523/.claude/skills/esp32-debugging/SKILL.md); blob `b9172d76dee0f91a2c82880dfb121aa69fd69337`; SHA-256 `5ba2c29a4a4eb5356b6302e957ea3bf2a0d5d289e1b31881a4d652ad9b61d767` | MIT, copyright 2024 Lauri Gates, pinned root LICENSE. ADAPT diagnostic classification, reject project-specific fixes. |

<a id="dispositions"></a>
### Line-level disposition and adaptation

Each source key resolves to the exact commit and path above; line ranges refer to those bytes. `KEEP` retains an audit observation, `ADAPT` denotes the attributed project rewrite proposed here, `DUPLICATE` means use the existing Standard row instead, `REJECT` means exclude the instruction/artifact, and `PENDING` forbids adoption until resolved. None means approved execution. License clearance for U1/U2/U3 would require a fresh scoped review before any use; these workflows were independently authored from project/vendor sources.

| Source locator | Capability/rule relationship | Disposition and reason | Review owner / verification |
|---|---|---|---|
| [U1 lines 19–35](https://github.com/pedrominatel/awesome-esp-ai/blob/ed3956d8572f7d179a96887d66fbf089d1502720/skills/esp-idf/SKILL.md#L19-L35) | FW-IDF-001 | PENDING license; candidate build/toolchain coverage recorded, no wording adopted. Project ADR-0003/vendor sources support the independent workflow. | Owner/license reviewer, Embedded; license unresolved |
| U1 lines 37–81 | GOV-004/009, FW-HW/DBG | DUPLICATE existing authorization boundaries; REJECT automatic target/clean/install/probe/flash action for this Issue. | Embedded/Security; no hardware action |
| U1 lines 83–106 and `component_registry.md` lines 49–63 | C-006/ERR-001, FW-CMP | DUPLICATE code constraints; PENDING prose license; registry discovery/add-dependency is not imported. | Embedded/Owner; no network package install |
| [U2 lines 16–48](https://github.com/pedrominatel/awesome-esp-ai/blob/ed3956d8572f7d179a96887d66fbf089d1502720/skills/esp-idf-components/SKILL.md#L16-L48) | FW-CMP-001 | PENDING prose license; REJECT registry-first/scaffold default and package installation as a local-component requirement. | Embedded/license reviewer |
| U2 lines 50–95 | C-004/006, ARCH-001/004 | DUPLICATE Standard component/interface constraints. Independent vendor CMake procedure used instead. | Embedded; exact SDK check required |
| U2 lines 97–138 and component-template subtree | FW-CMP-001 | REJECT publishing/CI/package templates for internal placeholders; template-local license does not clear the whole skill. | Owner/Security; not imported/executed |
| [U3 lines 11–40](https://github.com/adamlipecz/esp32-firmware-engineer-skill/blob/2d5737faed742c09dfe89197871b635e7608376b/esp32-firmware-engineer/SKILL.md#L11-L40) | GOV/QA, FW-HW | DUPLICATE scope/hardware input checks; PENDING license. Upstream ask-on-any-ambiguity is not an additional project approval flow. | Embedded/Owner |
| U3 lines 42–90, 120–138 | MEM/ERR/RTOS/RAD, FW-RTOS/DBG | PENDING license; overlapping constraints link to Standard only. References inventoried; no prose adoption or API approval inferred. | Embedded/Security; independent vendor procedure |
| U3 lines 92–104, 140–146; bundled scripts/templates | FW-IDF/CMP/HW | REJECT wrapper import, shell-profile edits, plugin check, OTA/display/partition templates. No extra framework or SDK version adopted. | Owner/Security; static execution review below |
| [U4 lines 18–38](https://github.com/magnus919/agent-skills/blob/f4950d8743b6590762b3227b8ba9ecc55b936855/esp32-development/SKILL.md#L18-L38) | FW-HW-001, QA-001/003 | ADAPT host-first board/power/port evidence into a WROOM/ESP-IDF procedure. KEEP the source's distinction between discovery and physical proof as an attributed workflow idea; project rules retain constraints. | RF/Hardware/Security; PROPOSED |
| U4 `references/hardware-and-electrical-safety.md` lines 5–39, 65–84; `references/debugging-recovery-and-security.md` lines 5–42 | FW-HW-001 | ADAPT physical fault-isolation sequence and power/reset hypotheses; use exact manufacturer/PCB facts, no generic pin/voltage table or fixed experiment count. | RF/Hardware; actual PCB input pending |
| U4 `references/hardware-test-automation.md` lines 5–24, 28–47, 67–80 | QA-001/002/003/008, evidence contract | ADAPT attempt/fixture/artifact accounting; project evidence tiers and Host provenance remain authoritative. No test automation/helper imported. | Security/QA/Owner; physical tests NOT_RUN |
| U4 lines 5, 40–85 and templates/scripts | FW-IDF/HW | REJECT alternative frameworks, demo GPIO/flash/scan instructions and helper execution. Broad upstream capability is not project scope. | Embedded/Owner; scripts not run |
| [U5 lines 54–95](https://github.com/laurigates/mcu-tinkering-lab/blob/34437ae5875057d4d407886ab3c9b8f84f6ea523/.claude/skills/esp32-debugging/SKILL.md#L54-L95) | FW-DBG-001, MEM/ERR/QA | ADAPT symptom categories to hypothesis-led diagnosis with exact-image evidence. REJECT automatic stack growth and certainty from a corrupted return register. | Embedded/QA; vendor API review |
| U5 lines 3–6, 28–52, 97–148 | FW-IDF/CMP/HW/DBG | REJECT tool allowlist, `just`/clean/monitor commands, old `driver`/I2C assumptions, generic pull-up/stack constants and automatic Kconfig changes. DUPLICATE existing memory/error checks. | Embedded/Security; no commands executed |
| U5 lines 69/87, linked gated-init rule and PCA9685 test | FW-DBG-001 | REJECT robocar/XIAO/PCA9685 project-local rules/test import. Source-specific event observations are not evidence for SX1276 or a universal panic diagnosis. | Embedded/QA; transitive project dependencies NOT_VERIFIED, not adopted |
| None of the five | FW-RAD-001/FW-TDMA-001 | KEEP as identified capability gap; independent project/vendor procedures added. No unsupported upstream Custom MAC/TDMA coverage claim. | RF/Embedded; HIL/RF NOT_VERIFIED |

### Executable, dependency and prompt review

| Source/artifact group | Static observation and dependency/side-effect boundary | Decision |
|---|---|---|
| U1 SKILL/registry reference, root README | Invokes IDF/EIM/esptool and registry metadata/archive endpoints; README advertises `npx skills add`. Package/setup actions can write files or fetch code. No bundled script under the selected U1 subtree. | PENDING license; REJECT install/activation instructions. No EIM/esptool/registry actions run. |
| U2 reference/template/CI | CMake/source/manifest examples, external component-manager `latest` documentation and workflow actions include build/package/upload authority and possible credentials/publication. Cached clangd index is a binary artifact. | REJECT templates/workflows/index. No dependency resolution, CI, packaging or upload. No claim that external action dependencies are audited. |
| U3 shell wrappers/common.sh | Source shell environment candidates including `esp-idf-v5.*`, select target through `idf.py set-target`, create build paths, invoke tools and chain flash/monitor. Tool availability check does not enforce exact v6.1. | REJECT all wrappers; no sourcing or shell-profile change. |
| U3 compatibility checker | Executes local idf/git commands, scans project files, may fetch floating ESP-ADF `master` README and writes an evidence report; plugin heuristics are unrelated to this MVP and not exact-stack proof. | REJECT checker and compatibility lock example; no ADF/SR dependency introduced. |
| U3 validate.sh | Uses a developer-specific absolute validator path, creates a venv and may install unpinned PyYAML. Compiled Python cache is not reviewed executable source. | REJECT validator/cache; not run. |
| U3 references, templates, agent YAML | Cover OTA/partitions/eFuse/security/display/console/shell setup beyond scope, with code/config mutation and irreversible-action examples. Agents can activate instruction/tool policy. | PENDING prose license, REJECT template/agent activation and security provisioning. No transitive external dependency approval. |
| U4 esp32-preflight.py | Static source uses stdlib filesystem globs/platform/shutil for tool/port discovery without opening serial ports; self-test is available upstream. Tool/path inventory can reveal host metadata if published. | REJECT import/execution here; no script or self-test run. Host discovery uses reviewed native commands. |
| U4 templates/evals/references | Includes ESP-IDF GPIO, MicroPython I2C scan, ESPHome secrets example and other frameworks; some commands/fixtures flash/reset hardware. Source-index URLs use floating current docs; they are not permission or evidence. | No template/eval execution/import. Only cited MIT workflow ideas adapted; external links not transitively trusted. |
| U5 skill frontmatter and project references | Requests `Bash(just:*)`, `$ARGUMENTS` processing and project-local recipes. Linked PCA9685 test includes local driver/shim dependencies; related rules point to additional repo/user-local material. | REJECT tool grants and project commands/rules/test imports. Test dependencies/user-local files NOT_VERIFIED, no adopted content depends on them. |

All five contain imperative agent text; it was treated as audit data. Static review found the concrete mutation/version/activation risks above. It does not establish absence of malicious behavior or full dependency safety. No credentials were supplied to upstream tooling and no upstream program was executed. Human reviewers can resolve provenance/license or compatibility questions later without changing this Issue's write scope.

<a id="licensing"></a>
## Attribution and licensing

The limited U4/U5 workflow adaptations above credit Magnus Hedemark's `esp32-development` and Lauri Gates's `esp32-debugging` at their exact pinned revisions. Original project/vendor procedures are identified separately. The upstream MIT permission and warranty notice is retained below for each adaptation; one shared text follows both copyright notices. U1/U2/U3 content is not reproduced/adapted as guidance because its applicable prose license remains unresolved. Manufacturer documentation is linked and paraphrased for task locators, not copied as a substitute manual.

```text
MIT License

Copyright (c) 2026 Magnus Hedemark
Copyright (c) 2024 Lauri Gates

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

License sources: [U4 LICENSE.md](https://github.com/magnus919/agent-skills/blob/f4950d8743b6590762b3227b8ba9ecc55b936855/LICENSE.md), [U5 LICENSE](https://github.com/laurigates/mcu-tinkering-lab/blob/34437ae5875057d4d407886ab3c9b8f84f6ea523/LICENSE). Template-local [U2 Apache text](https://github.com/pedrominatel/awesome-esp-ai/blob/ed3956d8572f7d179a96887d66fbf089d1502720/skills/esp-idf-components/component-template/template/license.txt) is inventoried for audit only and is not a grant inferred for sibling prose.

<a id="verification-record"></a>
## Verification record and unresolved work

This deliverable is `PLAYBOOK_DRAFTED / ROUTER_NOT_IMPLEMENTED / SKILLS_NOT_INSTALLED / HIL_RF_NOT_VERIFIED`. Source pin/hash inventory and static audit were performed; no upstream scripts were executed. Document validation, scope/diff/quality receipts, exact final head, fresh Auditor findings and Draft PR URL belong in the Coordinator's delivery evidence/PR, bound to the final candidate. This text itself is not a claim that those later checks passed.

Issue #102 changes only this Markdown file. No firmware build, simulation, hardware probe/monitor, flash, RF transmission, legal assessment, HIL/timing test, skill installation or router activation was run for this documentation work. Those dimensions are `NOT_RUN / NOT_VERIFIED`, not failures of the proposed workflows. Required human technical/Owner reviews remain PENDING. U1/U2/U3 prose-license resolution is PENDING and blocks their adoption. PCB/radio-revision applicability and all dependent physical procedures remain NOT_VERIFIED until actual task inputs exist.

<a id="file-inventory"></a>
## Pinned file inventory, audit appendix

The following inventory covers every file in the five selected skill subtrees, root README/license files and U5's directly named project-local rule/test. No reference/script/template is imported into the repository; scratch copies are audit data only. U1/U2 share a repository, so their shared root README is listed once. Aliases `awesome`, `engineer`, `development` and `debugging` resolve respectively to the U1/U2, U3, U4 and U5 repositories and their immutable commits in the five-source table. SHA-256 is over raw blob bytes, not rendered text. The Host inventory also records Git blob IDs/byte and line counts. Binary caches are rejected, never loaded/executed.

References inside rejected project-local examples can lead to broader driver/shim/build rules and user-local files. Those transitive project dependencies are NOT_VERIFIED and excluded, not silently adopted. Likewise external tool packages, registry archives, linked videos and floating documentation URLs are not dependency approvals. Only the explicitly cited U4/U5 workflow ideas and exact vendor/project authority inform the proposed procedures.

| Repository alias | Exact path | SHA-256 | Audit disposition |
|---|---|---|---|
| `awesome` | `README.md` | `f993e135cb6d7ebc321ff8c18bd52c4d4ce6eebbf59179f3d0ddb71ee1723249` | KEEP audit locator only; no install instructions adopted |
| `awesome` | `skills/esp-idf/SKILL.md` | `16041d792367a20c0548a1aa440ecd42d7a242e80cf511b95515aa14163f9046` | PENDING prose license |
| `awesome` | `skills/esp-idf/component_registry.md` | `fef4954863828228c16c8b5e04d54945e275eed9daeee956ec2bde3d1260b07e` | PENDING prose license |
| `awesome` | `skills/esp-idf-components/SKILL.md` | `a82676b30bbae66943d8e74f0784c99d7c982c4acf09da8307f6a5345bb958ed` | PENDING prose license |
| `awesome` | `skills/esp-idf-components/component-template/.github/workflows/upload_components.yml` | `872f2f629076a90ec19d1f0396024b740df3e11e937e5e71a1aaf949b8ffd347` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/.github/workflows/validate_component.yml` | `2072233c3eee9fad7cb5d3cab6e22afecf3886dca8523ada1396c310ddea8fe5` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/examples/example_template/.cache/clangd/index/example_template.c.B23F46179A1CE2CF.idx` | `31cac31c92ac83ffb9e2d32aa7269125ddb5e156c112cbc5eeb7bab0661b24ff` | REJECT binary cache |
| `awesome` | `skills/esp-idf-components/component-template/examples/example_template/.gitignore` | `086146a1bb5ded93c6e8f4f0bcc0cefbc4f9198a764a7c41aa9ee5270cb7f899` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/examples/example_template/CMakeLists.txt` | `7e40d08424e3ce3da73d9ed900ad67a7ac827da9d66e8a570cfd3207e22c4f53` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/examples/example_template/main/CMakeLists.txt` | `fcb1488da3374689a9fecc499e065d7399396ed8f3631ff988c46ccc78d8cb7b` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/examples/example_template/main/example_template.c` | `547a793f96e6d6d76c8edbbc5860dc6b910da72b7e742a1634b6480fdaf64535` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/examples/example_template/main/idf_component.yml` | `9382d62619e57b452a49198dc3e2e7424ac57cc16f123fb17bbdf40a6a1de49d` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/template/CMakeLists.txt` | `cf5af940d33b59e7e7bcc6adead5808f040c69b513af4997ba46e48c99ba2058` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/template/README.md` | `a34bc7534f5e18c37ef91e4e449e9e9ec4045aba7c3420a7e28a72460d1850eb` | PENDING prose license |
| `awesome` | `skills/esp-idf-components/component-template/template/idf_component.yml` | `a604b1e874dd888133f464bae4498f82564fad2ea29d943da68c8f92f7cfc64e` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/template/include/template.h` | `8e38c7095a3b6d327750f6e417c8638bedd95deb6602520db091f2d0cc5bccff` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/template/license.txt` | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/component-template/template/template.c` | `1f2c8072a9ba8c573806ce4375afb16401358c920ecd3321c9b97e8eb0e06cb9` | REJECT template/workflow import |
| `awesome` | `skills/esp-idf-components/references/component_manager.md` | `65f0892add52510ec513614c99254c73cff915c878aa39a71c82ccad5e1d783c` | PENDING prose license |
| `engineer` | `README.md` | `f0381abfd104af1561d87a08c80baa9a1120245bf650849d6a52c58f597c5561` | KEEP audit locator only; no install instructions adopted |
| `engineer` | `esp32-firmware-engineer/SKILL.md` | `547d2304125b95434e70d1456fd670f99e78417075ded04e825c4af081e67ac5` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/agents/claude.yaml` | `dcbe7ca398bb8c2b38e0cd0028296450df3abdf4d0c6233aeb2ff559dc0744e3` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/agents/openai.yaml` | `454d79fb7d9aaccef3228cefcb375206c1fd32cc513e113facb1f9ce97e01060` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/compatibility/esp-framework-compat.lock.example` | `10144ac5735f32643a8db80a353949d43f9546834f6958c8db597b7a5270fa6a` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/display-flush/display_flush_template.c` | `cf1950f8f40504c48692a170744c32332c95d439d295984bec4cab158594d580` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/esp-console/CMakeLists.txt` | `fa81c347089b276d8e4f97b7c99b0d6ede417abbd40dc7e50a093acc3a58c1ed` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/esp-console/app_console_commands.c` | `c26d194500ea29458a1367718178309d0e01fc21c41541b684047b39ae8ada44` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/esp-console/include/app_console_commands.h` | `5be7a86fedabf6b419120e51f46585cf4be7053abd0b754c7d5bebcaeea87a64` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/esp-idf-component/CMakeLists.txt` | `3a1a99bb9c4de79eb2de7555c05558ce8c7fb30e28bd1375bca7bee8404d7261` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/esp-idf-component/esp32_component_template.c` | `1f387ac7b47c7b1bfbffeb2f14c0b011e0984688162ca69fa6773fc21d8d04cf` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/esp-idf-component/include/esp32_component_template.h` | `3e43f8c572756e872bb7d80f0cb646b3071641d56012912d71ae2a404740c895` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/partitions/ota_16mb_example.csv` | `fc4d9bb4e8ee5bea7237d4943ece3f5433feb694640f6df94f336f44897597ff` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/assets/templates/shell/zshrc-esp-idf-snippet.zsh` | `35e03be2a242b8742becc1831190ff96ea135393a059ea14db316ac2f55f1ce9` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/references/communication-protocols.md` | `0ce3a6b92642880faf67099beb829e6d0d1cb8984956af09c2baa2fbc4bc2561` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/dependency-compatibility.md` | `c4ea67206751c8cc78a4dccee47f038cf3b0f0a68203ed566500743b7796e469` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/device-terminal-console.md` | `5bd910ea773127578e34a0cf53fada4459441d5651fcbc59562c1660b7763730` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/display-graphics.md` | `b3cc25dcf7196cfd5006c2922c2f0ec245b8eec5a03b2ef6c85f5e632ee7b8e9` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/esp-idf-checklists.md` | `139324d122af5d34334389d61b2fa51e9caeead99d77bf1d734452e1f149c851` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/logging-and-observability.md` | `539963e45ef239e87dc6e4a9bf99b210b45b5499ddb76eb0e463873bfa8260c6` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/lvgl-display.md` | `fbb3104afdcbfe69ce4faeab4cf333d740d25bf3997f1180c9e994011db70e59` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/memory-optimization.md` | `65b3bd73acf1b7c5e5db4bad6a319b29edf42434d2006a1fae0afca282149894` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/microcontroller-programming.md` | `08ea205309c1e69c5031cad70e5ee1fb92157c585757336b92e70aecf7ee5878` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/ota-workflow.md` | `65c2458d4d41cc68530183f72d6f52881b98c4138605b80d8ffe1ac1140eb1a3` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/panic-log-triage.md` | `4051306c7b44cb21bd020e1a54b60f4052b79ad11beff8ac41b74d68be6ca529` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/partitions-and-sdkconfig.md` | `1ba1d9a2c0ab49db58996f0d4bb6c76b8bd3a7d7d8ba94a26fad2d5df1a868de` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/power-optimization.md` | `89f0d75a7f362c619b45aa9f8164d409e1c05743917c59e5148bf9807144ad21` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/rtos-patterns.md` | `69496d91607b2c4d6ec83142059a1783a79e49f94c4fd7631b51d4ee5df3f64c` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/security-hardening.md` | `86e0a8fbb5e85a97844d1ce22dda2f5ce3f506f3f2ec0847f76355c1b9192e34` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/toolchain-and-shell-setup.md` | `25e1eab6c1ca2e3cc140272843c845d8902bf012a258292bc6844f2546e97f3b` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/references/values.md` | `b0dc256978b28ee0f74c5de57dee076af9f4c9e73a239547dfe857fa03788211` | PENDING prose license |
| `engineer` | `esp32-firmware-engineer/scripts/__pycache__/check_plugin_compatibility.cpython-314.pyc` | `ac1545bbc2bcffc62f7ec23aeafa26837efdcd15a03071a395591ab3a19c14d9` | REJECT binary cache |
| `engineer` | `esp32-firmware-engineer/scripts/build.sh` | `f51913137f57a557aca53eae1a29a84bc581ab049e916bd5aa7a7185d1c0f900` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/scripts/check_plugin_compatibility.py` | `1d03362d00b894ac6eb10eacc974999cbec8066e84d1efe1d16cffcbb774946e` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/scripts/common.sh` | `771771954393b4cdd9eaf6718ab1b97a1ebe5662eb071de4aa31bd9b81f3b957` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/scripts/flash.sh` | `4f0e454846a58349218b6b71de6045eebc45edb49c58857ccbc709ab54566404` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/scripts/flash_monitor.sh` | `c2ecee0d5f895e31b46272bbf82d688643a89a58bb937db64b4e6a472c1fad21` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/scripts/menuconfig.sh` | `ec472334daa2f4d9b6f0c305ae02edbe3cf53c6c6ca3f37af6c3749f02e28cfc` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/scripts/monitor.sh` | `2f6eadd3953df121f9e9721ecee40fd70144d14796a89e7f9e09524aae10a063` | REJECT script/template/agent import |
| `engineer` | `esp32-firmware-engineer/validate.sh` | `a06e617655aba8d22f05eae75c9c2f8c17fcbdfbd433cb236c133fb568687392` | REJECT script/template/agent import |
| `development` | `LICENSE.md` | `22fa3b1ec405fe440e86d0d293ce21de0c637ebc37f263dbe3032ee47215cfe2` | KEEP MIT notice/provenance |
| `development` | `README.md` | `c53f76c3ea75086158dda6064572909cb471088f93c65d6dedad425f41ec8a1c` | KEEP audit locator only; no install instructions adopted |
| `development` | `esp32-development/README.md` | `0a8ca5b7ef235523ce30d2dfb7a59e8211fdc294eed757a9e7f4994c4cade4ca` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/SKILL.md` | `19b53675b50873d093c0e016c63af6fff1f7b3f05d0d4f58ac54a8edbef6329c` | ADAPT cited workflow ideas only |
| `development` | `esp32-development/evals/evals.json` | `da36f8bd66254ddb03fcb87f3cbd9c8338007839091c51770a086a8fa55ec9db` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/references/connectivity-power-and-ota.md` | `32963e22c6a7fec6ac9393da2764fe940d53565051f9f96097d247bc6105ebb6` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/references/debugging-recovery-and-security.md` | `149ea59175e358633f77e2e2e2b3733af8942aae220295fe8c5901ebf5878696` | ADAPT cited workflow ideas only |
| `development` | `esp32-development/references/decisions-and-preflight.md` | `da935c7ed49cc3fa104edceb2266f58ca04dc4ae2dd0da9a7c53bb4ca152ea7e` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/references/firmware-frameworks.md` | `e5fe73e0ae573eee7b1cff6498a313262697532f4b8f818c9cad0f670a1e17e5` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/references/hardware-and-electrical-safety.md` | `8e1983c854da1a364952cc7862ad21cc4370ed4fd4bc0df0db056b063239f069` | ADAPT cited workflow ideas only |
| `development` | `esp32-development/references/hardware-test-automation.md` | `621a27259cf2525ed5f9c14fd0142f192208bc86a5e79d1d0a41ff79ff9d55f5` | ADAPT cited workflow ideas only |
| `development` | `esp32-development/references/native-tool-workflows.md` | `0812a4e61b374c54a33aecbc62151620a74355dbdbcb5b2475611ea3cfcdce4c` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/references/peripherals-and-buses.md` | `73730cc94a0e2a9d833012731c46297cc92dceca3a451d3df6bd076530700aba` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/references/sensors-actuators-and-calibration.md` | `f5e0be61a5bdba4d470bfbf2a648c9772bd4cf9fc5e9b77eccef384566ab3f8d` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/references/source-index.md` | `72fed04c2d841d3e6e9837d5f4f7c44e7256bbab6debe09307b0760cf4a90b81` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/scripts/esp32-preflight.py` | `900461278e8e22d92d43b66834820565b6d7aa009cfcebf8f6276df34f3727dc` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/templates/component-contract.md` | `945bb63cff2c4150dd88517f3cffe9b5be7ccd5f2f6eabe17b542dfae2499501` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/templates/esp-idf-main.c` | `250567e2a9813734e5e4a8298f4322d97510a3e4439b22f5d8589b81eef38169` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/templates/esphome-device.yaml` | `3422baef58f68527087f2040ddbe73c62b1881f0ecd5c0267e6095fd38e3cc4a` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/templates/esphome-secrets.yaml.example` | `15606b6b52d2aa1307bdcc39855d69b07ab98b3cb345f303dbf37fb8763feda4` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/templates/hardware-bringup.md` | `8bc9eb3540837011ac26c37607a8279210b91b6a584cfe4e3495fc2156511933` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/templates/hardware-test-plan.md` | `1469137c1003ae6adecb789138ae2be0ec2a4fde21ab80c212b7c308cdbcc0b5` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/templates/micropython-i2c-scan.py` | `99d52ceae80057ca6b57cf34f324d61e82376d39f59c78fbb98f2b36afd1ea7d` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/templates/platformio.ini` | `f65e70c9a0191a43e0ade888647e83fd2a4757a96eafe392b1952d55b44b3334` | REJECT import/execution; reference navigation only |
| `development` | `esp32-development/templates/zephyr-esp32.overlay` | `6d0f3c6f1dbf02e87dee0cd88f3bc85548eb3a1aae7b8f19e2e764c9e154cb6d` | REJECT import/execution; reference navigation only |
| `debugging` | `.claude/rules/gated-init-paths.md` | `a7c0dbfd51629c191544b15263498d893efb12786fdf2ce3b3fd556fe7496384` | REJECT project-local rule/test import |
| `debugging` | `.claude/skills/esp32-debugging/SKILL.md` | `5ba2c29a4a4eb5356b6302e957ea3bf2a0d5d289e1b31881a4d652ad9b61d767` | ADAPT classification only |
| `debugging` | `LICENSE` | `d3386948332479ac837f27c043ff7f10e841830af2ab0bf33bfc7d348a8f7dc4` | KEEP MIT notice/provenance |
| `debugging` | `README.md` | `d8c3cb4f8642f2be440e4359d62a01c00f87733f335cdf9d00f0c1912af18378` | KEEP audit locator only; no install instructions adopted |
| `debugging` | `packages/robocar/unified/test/test_pca9685_multi.c` | `da8cce97883517e6f7f41110af282b6c154272566369b7755a44b316e4259f71` | REJECT project-local rule/test import |
