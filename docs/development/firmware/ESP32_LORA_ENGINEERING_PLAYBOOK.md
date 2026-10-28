<a id="task-index"></a>
## Task index
| Task or symptom | Proposed capability | Workflow | EXISTING_C_RULE_IDS | Initial evidence tier |
|---|---|---|---|---|
| SDK identity, configuration or build failure | `FW-IDF-001` | [Build and configuration](#fw-idf-001) | GOV-002/003/004; QA-001/002/005/006 | Host/build |
| Shared component, include or link failure | `FW-CMP-001` | [Component and CMake](#fw-cmp-001) | C-004/006/019; ARCH-001/004/006/007 | Host/build |
| Race, blocked task, ISR or timer handoff | `FW-RTOS-001` | [Concurrency](#fw-rtos-001) | RTOS-001–010; MEM-001/005/006; ERR-001/002/005 | Static, then unit/HIL as needed |
| Guru Meditation, watchdog, stack or core dump | `FW-DBG-001` | [Crash diagnosis](#fw-dbg-001) | MEM-003/004/007; ERR-003/007; RTOS-010; QA-001/003/005 | Existing artifacts, then authorized HIL |
| Board identity, USB/UART, reset or brownout | `FW-HW-001` | [Board diagnosis](#fw-hw-001) | GOV-004/008; RAD-007; QA-001/003/008 | Host discovery, then authorized bench |
| SX1276 SPI, RxDone, FIFO or register mismatch | `FW-RAD-001` | [Radio diagnosis](#fw-rad-001) | RAD-001/002/003/004/005/007/009; RTOS-001/003/008; ERR-001/002/005; QA-001/003/008 | Static/datasheet, then authorized HIL |
| Beacon loss, clock drift, ToA, guard or turnaround | `FW-TDMA-001` | [Timing diagnosis](#fw-tdma-001) | TDMA-001/002/005/006/007/008/009/010; RAD-006/008; ARCH-002/003; SEC-003/004; QA-002/003/008 | Static/simulation, then authorized HIL/RF |
| Ordinary documentation, no firmware behavior affected | None | [Manual selection](#selection-contract) | None | Document checks only |

Related sections: [authority](#authority), [capability mapping](#capability-mapping), [handoff design](#selection-contract), [negative cases](#selection-examples), [source audit](#source-audit), [file inventory](../../audits/firmware/UPSTREAM_SKILL_AUDIT_ISSUE_102.md#file-inventory), [licensing](#licensing), [verification record](#verification-record).
<a id="authority"></a>
## Authority and applicability
C Standard: [§0](C_CODING_STANDARD_V2.md#0-agent-entrypoint-execute-this-decision-flow), [§12](C_CODING_STANDARD_V2.md#12-blocked-decisions--never-resolve-in-coding-standard), [§13](C_CODING_STANDARD_V2.md#13-deterministic-agent-checklist-required-pr-evidence). Load applicable Rule IDs; Capability IDs route workflows and do not grant enforcement authority.
The supported architecture is C/FreeRTOS, ESP32-WROOM-32E and one SX1276 running Custom LoRa P2P MAC / Hybrid TDMA. Gateway executes the local radio schedule. The Go Backend plans future schedules over MQTT 5.0/TLS; it does not time RF slots. Arduino, PlatformIO, MicroPython, ESPHome, Zephyr, LoRaWAN, OTAA, adaptive-data-rate LoRaWAN procedures and ChirpStack are excluded. ESP32-S3/C3 examples do not establish WROOM-32E pins, flash/PSRAM configuration or native USB support.
The board revision, schematic, USB bridge, pin map, supply and fitted radio module are required task inputs for physical work. No specific PCB revision has been established by this document. `firmware/gateway_master/main/main.c` and `firmware/sensor_node/main/main.c` at the baseline are scaffolds. `firmware/components/{sx1276_driver,lora_mac,tdma_common,airtime_policy}/` contain README placeholders, with no implemented driver or timing test interface. Workflows describe how a future scoped task would investigate those features; they do not assert those features exist.

| Authority key | Exact source/revision and section | Status and use |
|---|---|---|
| `P-AGENTS` | [AGENTS.md](../../../AGENTS.md), baseline above; Git blob `0ca557b3d28db3c33c01dc1112ad65b1ee5f0647`; SHA-256 `aaa4a63bb551346fbd998f5cea868d97086d52b21fece21933f23fa4fafc8f89` | Execution scope and G0 entrypoint. A new task verifies its own current tracked bytes. |
| `P-C` | [C Standard](C_CODING_STANDARD_V2.md), §0/affected Rule IDs/§12/§13 | Owner-authorized reference (Issue #108); technical review/enforcement remain separate. |
| `P-ADR` | [ADR-0001](../../adr/0001-hybrid-tdma.md), [ADR-0003](../../adr/0003-esp-idf-v6-1.md), baseline above; decision sections | ADR-0001 architecture direction accepted; its R1 rationale remains draft/pending technical review. ADR-0003 exact `v6.1` baseline approved by Owner. `firmware/esp-idf-version.txt` is the toolchain input. |
| `P-OPEN` | [Open decisions](../../../contracts/OPEN_DECISIONS.md), baseline above, D01–D13 and unlock conditions | Preserve each row's distinct status. D01/D11 security/wire and D03 RF permission remain blocked. No numeric profile is approved here. |
| `P-MAC` | [Radio MAC](../../../contracts/radio-mac/specification.md) §1/§3/§4; [TDMA schedule](../../../contracts/radio-mac/tdma-schedule.md) §1–§4, baseline above | `0.1.0-draft`, security/wire not frozen; P-10S-15 is a proposed simulator profile. Read for candidate behavior, not production authority. |
| `P-REQ` | [Requirements](../../requirements/requirements.md), baseline above, FW-001–FW-004, MAC/SEC/INT rows | DRAFT with R1 baseline and R2 remediation; G0 NOT_VERIFIED. Proposed coverage, not approval evidence. |
| `P-GATES` | [Acceptance gates](../../verification/acceptance-gates.md), [Native Fast Lane](../harness-fast-lane.md), [quality gates](../harness-quality-gates.md), baseline above | Evidence types and actual Host receipts remain separate. Fast Lane is instruction-based orchestration, not a hard isolation claim. |
| `V-IDF` | ESP-IDF annotated tag `v6.1` dereferenced to commit `fff9895c82d744c7237be8847347bdd1b07c6643` | Vendor API/build authority for ESP32. Version-matched pages and immutable source links appear below. No substitution with `latest`, prerelease or patch. |
| `V-SX` | [Local Semtech datasheet](../../Books/SX1276_Datasheet.pdf), baseline above, Rev. 7, May 2020, §4.1/§4.3/§6.4/§7.2 | Manufacturer reference for the fitted revision; hardware reviewer confirms applicability and errata. No generic register access authorizes RF. |
| `V-ESP` | [Local WROOM datasheet](../../Books/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf), baseline above, v2.1, §1.2/§3/§4/§6/§8/§9 | Module identification, pins, strapping, electrical and peripheral/reference-circuit lookup. Board schematic remains missing. |

Repository source baseline for this workflow audit: `34678739880f09af9f779358820d8b8c2ade0873`. Recheck live Issue, hardware revision and approved ADR/contracts per task. [System overview](../../architecture/system-overview.md) cannot override approved ADRs; conflicts or out-of-scope writes → `STOP_AND_REPORT`.
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
## Coordinator / Worker / Auditor selection (manual; router not implemented)
1. **Coordinator/G0:** Read live Issue/AC/allowed paths, branch and read-only consumers. Trusted Host must run `python3 scripts/agent_harness/agent_context.py --repo <candidate>` and inject the complete `agent_input` per [AGENTS.md](../../../AGENTS.md). Missing or drifted verification → `BLOCKED / STOP_AND_REPORT`.
2. **Route:** Match observed triggers and affected paths to [task index](#task-index), deduplicate, and record selected/excluded Capability IDs and rationale. Docs-only tasks select none by default; unresolved classification → `NOT_VERIFIED`.
3. **Load:** Read Standard §0/§12/§13 plus applicable Rule IDs, authority pins and D01–D13 stops. Do not load all 104 rules or upstream skill content by default.
4. **Worker + Host:** Edit only within scope and record diff, rules, commands/exits, limits. Host independently gathers quality receipts, hashes and frozen artifacts; build/simulation never implies HIL/RF/security PASS.
5. **Auditor + handoff:** Fresh read-only Auditor checks identical AGENTS version, frozen diff and Host receipts; Host rechecks fingerprints. Drift, unresolved P0/P1 or pending human reviews block readiness. Commit to Issue branch and Draft PR for human review only; no automatic merge, RF TX/flash, skill activation or policy change.
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

Required reviewers are Embedded Gateway and Node, RF/Hardware, Security/QA and Project Owner. Record actual reviewer, reviewed SHA, finding disposition and approval evidence. The content freeze supplies no technical signature or policy activation. Preserve D01–D13 states. C Standard review, playbook review, build/CI, model audit, human security review, HIL/RF/timing and G0–G6 have separate evidence. GitHub Actions `OWNER_WAIVED` is not CI PASS.
<a id="source-audit"></a>
## Upstream sources — Cold Audit Archive
[U1–U5 provenance, dispositions, executable/dependency audit and SHA-256 inventory](../../audits/firmware/UPSTREAM_SKILL_AUDIT_ISSUE_102.md#source-audit). Do **not** activate or install U1–U5; U1/U2/U3 remain `PENDING_LICENSE` and only U4/U5 ideas are attributed. See retained [MIT notice](#licensing).
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
Current content status is `OWNER_APPROVED_FROZEN`; the Issue #102 delivery record was `PLAYBOOK_DRAFTED / ROUTER_NOT_IMPLEMENTED / SKILLS_NOT_INSTALLED / HIL_RF_NOT_VERIFIED`. Source pin/hash inventory and static audit were performed; no upstream scripts were executed. Document validation, scope/diff/quality receipts, exact final head, fresh Auditor findings and Draft PR URL belong in the Coordinator's delivery evidence/PR, bound to the final candidate. This text itself is not a claim that those later checks passed.
Issue #102 changes only this Markdown file. No firmware build, simulation, hardware probe/monitor, flash, RF transmission, legal assessment, HIL/timing test, skill installation or router activation was run for this documentation work. Those dimensions are `NOT_RUN / NOT_VERIFIED`, not failures of the proposed workflows. Required human technical reviews remain PENDING; Owner content approval is recorded in Issue #108. U1/U2/U3 prose-license resolution is PENDING and blocks their adoption. PCB/radio-revision applicability and all dependent physical procedures remain NOT_VERIFIED until actual task inputs exist.
