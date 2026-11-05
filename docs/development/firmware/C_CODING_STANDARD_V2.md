| Group | Rule IDs |
|---|---|
| GOV | GOV-001..010 |
| C | C-001..020 |
| MEM | MEM-001..008 |
| ERR | ERR-001..007 |
| RTOS | RTOS-001..010 |
| ARCH | ARCH-001..007 |
| SEC | SEC-001..008 |
| RAD | RAD-001..009 |
| MAC | MAC-001..007 |
| TDMA | TDMA-001..010 |
| QA | QA-001..008 |

Rule fields: `ID | scope | directive | verification | failure action`. Source mapping: §15. `STATIC(CG)` uses available CodeGraph for caller/owner inspection; unavailable tooling is `NOT_RUN`, never runtime proof.

## 1. GOV — agent safety, scope, authority (all firmware work)
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| GOV-001 | all | MUST follow approved Issue allowed paths **exactly**; new tests/docs are not implicitly allowed | STATIC | STOP |
| GOV-002 | all | MUST verify repository, `origin/main`, branch, clean worktree and applicable instructions before mutation; MUST_NOT edit `main` | STATIC | STOP |
| GOV-003 | all | MUST preserve approved ESP-IDF tag `v6.1`; MUST_NOT substitute floating tag, prerelease or other patch implicitly | BUILD/HUMAN | STOP |
| GOV-004 | all | MUST_NOT change RF region/frequency/power, GPIO/PCB, partition/eFuse, crypto/wire fields, MQTT/API/DB schemas or CI/settings without expressly scoped approval | STATIC/HUMAN | STOP |
| GOV-005 | all | MUST_NOT assume LoRaWAN, OTAA, ADR, ChirpStack or LoRaWAN MAC; implement only LoRa P2P Custom MAC within approved contracts | STATIC/HUMAN | STOP |
| GOV-006 | all | MUST mark unapproved numeric constants/benchmarks and demo-profile claims `TBD / NOT_VERIFIED`; MUST_NOT invent RF/HIL/security test outcomes | STATIC/HUMAN | STOP |
| GOV-007 | all | MUST classify changed public API, wire/version, persistence, scheduling and auth semantics for producer/consumer compatibility before code edits | STATIC(CG)/CONTRACT/HUMAN | STOP |
| GOV-008 | all | MUST_NOT expose passwords, tokens, keys, MAC/session secrets or sensitive dumps in code, tests, logs, commits or PR | STATIC/SECURITY | STOP |
| GOV-009 | all | MUST produce a Draft PR with actual test evidence and requested human reviewers; MUST_NOT auto-merge, auto-approve, flash or TX | STATIC/HUMAN | STOP |
| GOV-010 | all | MUST distinguish `OWNER_APPROVED_FROZEN` document guidance from APPROVED repository policy; do not claim this standard is effective merely because it exists | STATIC/HUMAN | STOP |
## 2. C — formatting, names, types and interface boundaries
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| C-001 | `*.c,*.h` | SHOULD maintain consistent project formatting in touched lines; MUST_NOT reformat unrelated files or rename interfaces without scope | STATIC | FIX |
| C-002 | `*.c,*.h` | MUST use descriptive `snake_case` identifiers, units in quantity names and namespaced symbols appropriate to actual component | STATIC | FIX |
| C-003 | `*.c` | MUST keep internal symbols `static` unless intentionally exported via reviewed public API | STATIC | FIX |
| C-004 | `*.h` | MUST declare public ownership, bounds, units, error values, execution context and lifetime for exposed functions | STATIC/HUMAN | FIX |
| C-005 | `*.h` | MUST protect public headers against duplicate inclusion; C++ linkage wrappers only if approved consumer needs C++ | BUILD | FIX |
| C-006 | components | MUST declare real CMake `REQUIRES/PRIV_REQUIRES` from exact v6.1 and current build graph; MUST_NOT import old demo role Kconfig pattern | BUILD | FIX |
| C-007 | all | MUST use `stdint.h` fixed-width types at registers/serialized boundaries and `size_t` for buffer lengths; validate narrowing and integer arithmetic | STATIC/UNIT | FIX |
| C-008 | all | MUST initialize state explicitly, validate nullable pointers/bounds and avoid undefined shift, overflow, signedness or alignment assumptions | STATIC/UNIT | FIX |
| C-009 | all | MUST_NOT define application wire width/endian/scale from a C struct or demo code; approved contracts own serialization | CONTRACT/HUMAN | STOP |
| C-010 | all | SHOULD avoid macros with side effects and global mutable state; any unavoidable shared state needs documented owner/synchronization | STATIC/HUMAN | FIX |
| C-011 | newly defined C functions | MUST default to descriptive lowercase `snake_case` with `<module>_<verb>_<object>` order; use explicit C-016..018 callback/task/ISR forms where relevant, with C-020 exceptions | STATIC | FIX |
| C-012 | exported functions / `*.h` | MUST namespace new public function names to their actual owning component and use distinct domain verbs; examples `sx1276_read_register`, `lora_mac_decode_frame`, `tdma_calculate_slot_offset` are illustrative, not implemented/approved API claims | STATIC/BUILD | FIX |
| C-013 | function behavior | SHOULD choose accurate verbs: `init/deinit` for lifecycle, `start/stop` for operations, `read/write` for I/O, `get/set` for accessors, `encode/decode` for codecs, `validate` for checking, `calculate` for derived values and `handle` for events; MUST_NOT conceal I/O, state changes or blocking behind misleading `get`/`calculate` names | STATIC/HUMAN | FIX |
| C-014 | Boolean predicates | SHOULD name `bool` predicates as `<module>_is_<condition>`, `<module>_has_<property>` or `<module>_can_<action>` when the actual return type is `bool`; MUST_NOT force an existing `esp_err_t`/status API into `bool` for naming consistency | STATIC/BUILD | FIX |
| C-015 | internal `.c` helpers | MUST keep non-exported functions `static` and avoid generic ambiguous names (`process_data`, `do_work`, `helper1`); SHOULD retain a clear owner prefix unless truly unambiguous within the translation unit | STATIC | FIX |
| C-016 | FreeRTOS task entry | MUST use `<module>_<purpose>_task` for newly defined task entry functions (e.g. `tdma_executor_task`) and validate the actual FreeRTOS entry signature/ownership; MUST_NOT treat a normal helper as a task solely because of its name | STATIC/BUILD | FIX |
| C-017 | hardware IRQ | MUST reserve `<module>_<source>_isr_handler` for actual interrupt-context handlers (e.g. `sx1276_dio0_isr_handler`); task-context processing uses action names such as `sx1276_handle_irq_event`, never the ISR suffix | STATIC/HIL | FIX |
| C-018 | event/timer callbacks | MUST use `<module>_<event>_callback` for newly defined registered callbacks (e.g. `tdma_slot_timer_callback`) and document API-defined signature and actual TASK vs ISR dispatch context; name alone is NOT context or IRAM-safety evidence | STATIC/BUILD/HIL | FIX |
| C-019 | existing public symbols | MUST_NOT rename exported functions, callback types or external linkage solely to satisfy a naming proposal; changes to public interfaces require explicitly authorized scope, cross-component caller review and compatibility evidence | STATIC/CONTRACT/HUMAN | STOP |
| C-020 | framework-defined entrypoints | MUST preserve required SDK/standard/library names and callback signatures (e.g. `app_main`) even when they differ from project naming pattern; record exceptions rather than silently wrapping, breaking or renaming them | STATIC/BUILD | FIX |

**Function-naming examples (illustrative only, not approved interfaces):** `sx1276_read_register`, `lora_mac_decode_frame`, `tdma_calculate_slot_offset`, `tdma_is_schedule_valid`, `tdma_executor_task`, `sx1276_dio0_isr_handler`, `sx1276_handle_irq_event`, `tdma_slot_timer_callback`. Default naming applies to **newly defined functions**, not retroactive public API renames; ISR/timer execution context and return types must be checked against the actual ESP-IDF v6.1 API and active design.
## 3. MEM — bounded resource ownership and lifetime
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| MEM-001 | all | MUST define producer, consumer, owner, capacity and lifecycle of every queue, buffer and object crossing task/module boundaries | STATIC/UNIT | FIX |
| MEM-002 | steady-state | SHOULD use static buffers or bounded preallocated pools; MUST_NOT add unbounded repeated allocation in time-critical radio paths | STATIC/HIL | FIX |
| MEM-003 | all | MUST check allocation/creation results and handle exhausted resources without out-of-bounds access or uncontrolled TX | STATIC/UNIT | FIX |
| MEM-004 | all | MUST validate length/capacity before copy, append, parse or DMA transfer; maintain explicit `len <= capacity` invariant | STATIC/UNIT | FIX |
| MEM-005 | all | MUST document ownership transfer and buffer lifetime through asynchronous SPI/queue callbacks; no stack pointer surviving owner frame | STATIC/HIL | FIX |
| MEM-006 | all | MUST bound queue full/drop/retry paths with counters or reason codes and defined loss policy; MUST_NOT claim infinite offline retention | UNIT/INTEGRATION | FIX |
| MEM-007 | all | MUST derive stack/heap/pool sizes from reviewed budgets and measured load; MUST_NOT import old `256B` cutoff or demo queue lengths | HIL/HUMAN | STOP |
| MEM-008 | SPI/DMA | MUST verify exact ESP-IDF v6.1 DMA buffer capability, alignment, ownership and transaction completion before adopting DMA-specific assumptions | STATIC/HIL/HUMAN | STOP |
## 4. ERR — errors, diagnostics, recovery
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| ERR-001 | all | MUST check `esp_err_t`, FreeRTOS creation/queue results and hardware return paths; propagate meaningful error or documented fallback | STATIC/UNIT | FIX |
| ERR-002 | all | MUST enforce finite timeouts, retries and recovery budgets on SPI/radio/network and semaphore waits (except justified nonblocking owner loops) | STATIC/HIL | FIX |
| ERR-003 | all | MUST distinguish malformed input (recoverable rejection) from broken internal invariants (controlled fail-safe); no indiscriminate reset/assert policy | UNIT/HUMAN | FIX |
| ERR-004 | all | MUST make queue full, stale schedule, CRC/auth failure, radio timeout and airtime denial observable without leaking credentials | UNIT/HIL/SECURITY | FIX |
| ERR-005 | all | MUST use reviewed radio-owner-mediated recovery when modem state becomes uncertain; MUST_NOT reset/reconfigure bypassing ownership | HIL/HUMAN | STOP |
| ERR-006 | all | MUST_NOT interpret SX1276 `TxDone` as peer receipt, RF ACK as actuator execution, or MQTT `PUBACK` as business acceptance | UNIT/INTEGRATION | FIX |
| ERR-007 | all | SHOULD include reason codes, bounded telemetry and useful context in logs; MUST_NOT log raw secret/session material | STATIC/SECURITY | FIX |
## 5. RTOS — FreeRTOS tasks, ISR and timers
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| RTOS-001 | radio | MUST designate a **single Radio Owner** that serializes SX1276 SPI access and modem-state transitions; mutex alone does not authorize concurrent state machines | STATIC(CG)/HIL | STOP |
| RTOS-002 | all | MUST use bounded task/queue/message ownership, finite blocking where justified and init-before-enable ordering for IRQ/events | STATIC/HIL | FIX |
| RTOS-003 | hardware ISR | MUST_NOT perform SPI, network I/O, blocking, unapproved logging or allocation; timestamp/notify through context-safe bounded mechanisms | STATIC(CG)/HIL | STOP |
| RTOS-004 | ESP timer | MUST identify `ESP_TIMER_TASK` vs `ESP_TIMER_ISR` dispatch and corresponding Kconfig before choosing APIs; timer callback ≠ always ISR | STATIC/BUILD | FIX |
| RTOS-005 | task-dispatched timer | MUST keep callback short/nonblocking; defer work to an owned bounded task/queue, avoiding timer-task starvation | STATIC/HIL | FIX |
| RTOS-006 | ISR-dispatched timer | MUST use only ISR-safe APIs and applicable v6.1 dispatch/yield semantics; MUST_NOT assume `portYIELD_FROM_ISR` is correct inside esp_timer ISR callback | STATIC(CG)/BUILD/HIL | STOP |
| RTOS-007 | IRQ/timer | MUST prove task priorities/affinity/ISR latency/guard budget with actual board/config if claiming hard timing; source review alone is insufficient | HIL/RF | STOP |
| RTOS-008 | all | MUST define overflow behavior for ISR→task and event queues, verify startup order and tolerate late events/reboot safely | UNIT/HIL | FIX |
| RTOS-009 | all | MUST coordinate shutdown/recovery with in-flight ISR, DMA, tasks and timers; MUST_NOT free a buffer or callback context while still referenced | STATIC/HIL | FIX |
| RTOS-010 | all | MUST treat watchdog configuration, per-task liveness and fault reset as reviewed design—not proof of recovery from merely enabling WDT | HIL/HUMAN | STOP |
## 6. ARCH — component and dependency ownership
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| ARCH-001 | shared components | MUST keep `sx1276_driver` for registers/SPI/radio state, `lora_mac` for framing/security, `tdma_common` for schedule utilities and `airtime_policy` for admission, subject to actual repo boundaries | STATIC/BUILD | FIX |
| ARCH-002 | gateway | MUST keep Gateway as local TDMA real-time executor; Backend computes/version-controls future schedules and MUST_NOT command per-slot TX instants | STATIC/CONTRACT | STOP |
| ARCH-003 | node | MUST use authenticated Beacon/mapping and validated slot/priority conditions before periodic TX; unsafe sync ⇒ suppress affected TX | UNIT/HIL | STOP |
| ARCH-004 | all | MUST check interface/ABI changes across Gateway/Node, radio codec, MQTT, Go, React/Flutter; breaking interface requires explicit approval and tests | STATIC(CG)/CONTRACT/HUMAN | STOP |
| ARCH-005 | all | MUST_NOT silently add Redis, InfluxDB, extra services or LoRaWAN stacks to the MVP | STATIC/HUMAN | STOP |
| ARCH-006 | all | MUST_NOT assume scaffold equals operational SX1276 driver/TDMA stack; claim implemented features only when verified from live code | STATIC/HUMAN | STOP |
| ARCH-007 | all | SHOULD keep file dependencies acyclic and public API minimal; changes beyond Issue-authorized components need scope amendment | STATIC(CG)/BUILD | FIX |
## 7. SEC — parsing, secrets, replay, protocol boundaries
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| SEC-001 | RF receive/parser | MUST reject invalid length, version, direction, destination, reserved bits and unsupported frame type before field dispatch or side effects | UNIT/SECURITY | STOP |
| SEC-002 | wire | MUST serialize and parse explicit octets with checked offsets/lengths; MUST_NOT cast packed C structs to production wire protocol | UNIT/CONTRACT | STOP |
| SEC-003 | RF | MUST_NOT present CRC/PHY CRC as cryptographic authentication, integrity against an attacker or replay protection | STATIC/SECURITY | STOP |
| SEC-004 | crypto | MUST_NOT generate production MIC/AEAD/tag/wire codec or choose cipher, nonce, session/key layout while D01/D11 remain BLOCKED | HUMAN/CONTRACT | STOP |
| SEC-005 | crypto | MUST require key-scoped nonce uniqueness across resets/directions/rollover; when safety cannot be proved, block affected TX until approved recovery | SECURITY/HIL | STOP |
| SEC-006 | crypto | MUST bind replay state to authenticated identity/session/direction and authenticate control/ACK; exact format awaits reviewed contract | SECURITY/CONTRACT | STOP |
| SEC-007 | network | MUST keep MQTT TLS/principal/topic ACL and Backend API AuthN/RBAC as different trust boundaries; D13 credential mechanism remains unresolved | INTEGRATION/SECURITY | STOP |
| SEC-008 | integration | MUST preserve distinct RF replay identity vs MQTT event dedup identity; RF 8-bit seq is not a durable application idempotency key | UNIT/INTEGRATION | FIX |
## 8. RAD — SX1276 radio owner, PHY and airtime
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| RAD-001 | driver | MUST use current approved SX1276 revision datasheet to justify register address/mask/mode-specific behavior; no copying demo constant without provenance | STATIC/HIL/HUMAN | STOP |
| RAD-002 | driver | MUST serialize SPI commands and IRQ-driven modem transitions through Radio Owner; validate observed mode, FIFO and IRQ lifecycle on actual hardware | STATIC(CG)/HIL | STOP |
| RAD-003 | driver | MUST_NOT assume `IRAM_ATTR` alone guarantees every ISR call/data access is IRAM-safe; review actual build/config/call graph | STATIC(CG)/HIL | STOP |
| RAD-004 | driver | MUST check SPI/DIO event ordering, stale IRQ flags and TxDone/RxDone timeout/failure handling; no unsupported latency guarantee | HIL | FIX |
| RAD-005 | PHY | MUST_NOT hardcode or inherit 915 MHz, 921.4 MHz, SF/BW/CR, PA route, output power, channel or antenna approval from v1 demo | HUMAN/RF | STOP |
| RAD-006 | RF TX | MUST require **approved local airtime/RF admission** for every Beacon, data, ACK, alert, join and retry; no priority/emergency bypass | UNIT/HIL/RF | STOP |
| RAD-007 | driver | MUST keep board revision, GPIO/strapping, PA path, region/legal policy and RegVersion acceptance outside coding-style rules; consult approved hardware/driver spec | HUMAN/HIL/RF | STOP |
| RAD-008 | RF | MUST_NOT treat CAD as collision-free guarantee, `TxDone` as successful peer reception or RSSI/SNR alone as regulatory verification | UNIT/HIL/RF | STOP |
| RAD-009 | driver | SHOULD separate SPI HAL from radio state machine and make transaction ownership, timeouts and event reporting observable | STATIC/HIL | FIX |
## 9. MAC — custom binary MAC implementation gates
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| MAC-001 | MAC codec | MUST use only an **approved** versioned Radio MAC contract for production bytes; v0.1 8-byte header, CRC16 and 8-bit SCHED_VER are legacy candidates | CONTRACT/HUMAN | STOP |
| MAC-002 | MAC parser | MUST parse untrusted RF bytes with strict bounds and validate auth/replay before business/action side effects; fail closed on missing design approval | UNIT/SECURITY | STOP |
| MAC-003 | schedule codec | MUST_NOT truncate Backend schedule version to 8 bits, infer order via modulo-256 or accept unsafe rollover/reset mapping | CONTRACT/UNIT | STOP |
| MAC-004 | retransmission | MUST bound retry/backoff/ACK behavior, account for airtime and preserve anti-replay requirements; limits not invented by coding standard | UNIT/HIL | FIX |
| MAC-005 | shared codec | MUST coordinate Gateway/Node/Backend producer/consumer schema and golden-byte vectors before protocol freeze; compile-only not conformance | CONTRACT/SECURITY | STOP |
| MAC-006 | application data | MUST derive sensor scaling/units from versioned config/contract; no universal legacy ADC/channel scaling assumption | UNIT/CONTRACT | STOP |
| MAC-007 | tests | SHOULD cover negative tests for malformed, truncated, wrong-version, wrong-destination, replayed, wrap/reset and invalid-auth frames **after** wire/security approval | UNIT/SECURITY | FIX |
## 10. TDMA — schedule and clock behavior (no numeric freeze)
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| TDMA-001 | gateway | MUST validate request identity, authenticated origin, version, expiry/clock confidence, resource/slot ownership and airtime before staging a schedule | UNIT/CONTRACT | STOP |
| TDMA-002 | gateway | MUST persist valid shadow before `STAGE_ACK`, announce for required **complete** cycles, and activate only at a local superframe boundary | UNIT/HIL | STOP |
| TDMA-003 | backend boundary | MUST distinguish `PROPOSED/SENT/STAGED/ACTIVE/REJECTED/EXPIRED`; `ACTIVE` needs correlated actual `ACTIVE_REPORT`, not MQTT `PUBACK` | CONTRACT/INTEGRATION | STOP |
| TDMA-004 | backend boundary | MUST_NOT invent `EXPIRED→ACTIVE` transition on late `ACTIVE_REPORT`; reconcile per reviewed contract or report BLOCKED | CONTRACT/HUMAN | STOP |
| TDMA-005 | gateway/node | MUST distinguish proposal `expires_at` from unapproved active schedule lease; offline active continuation only under reviewed validity/safety policy | UNIT/HIL/HUMAN | STOP |
| TDMA-006 | clocks | MUST distinguish UTC for expiry, monotonic local deadlines and Beacon-derived RF slot synchronization; reset/jump/holdover mapping not inferred | HIL/HUMAN | STOP |
| TDMA-007 | node | MUST suppress periodic TX when authenticated mapping/sync/guard assurance is inadequate; missed-Beacon numeric limit remains candidate | HIL/RF | STOP |
| TDMA-008 | RF timeline | MUST validate full Beacon/DL/PCSS/DATA/ACK/JOIN/guard timeline, including JOIN→next Beacon spill, against one half-duplex radio | UNIT/HIL/RF | STOP |
| TDMA-009 | alarms | MUST bound priority contention and account for ACK/retry and airtime; `<3 s` is research target, not an approved SLA | SIM/HIL/RF | STOP |
| TDMA-010 | profile | MUST_NOT treat 10-second superframe, 15 slots, 400ms slot, fixed IRQ jitter or guard as measured/approved production parameters | HUMAN/HIL/RF | STOP |
## 11. QA — evidence, testing and claim discipline
| Rule ID | Scope | Directive | Verify | If violated |
|---|---|---|---|---|
| QA-001 | all | MUST link every result to Issue, exact commit, compiler/ESP-IDF version, board revision if relevant, command, environment, timestamp, expected/actual and artifact | HUMAN | FIX |
| QA-002 | all | MUST report distinct `CODE_WRITTEN`, `BUILD_VERIFIED`, `AUDIT_PASS`, `SIMULATION_VERIFIED`, `HIL_VERIFIED`, `RF_VERIFIED`; missing dimension `NOT_VERIFIED` | HUMAN | FIX |
| QA-003 | all | MUST NOT infer RF/legal, TDMA timing, HIL behavior, crypto safety, or production security from source review, CI or schema syntax PASS | HUMAN | STOP |
| QA-004 | parser/codec | MUST test boundaries/negative cases at relevant layer; JSON Schema cannot establish RF replay, topic ACL or schedule collision/clock correctness | UNIT/CONTRACT/SECURITY | FIX |
| QA-005 | firmware | MUST run actual Gateway/Node builds using exact v6.1 **when claiming those builds**; state `NOT_RUN` if unavailable | BUILD | FIX |
| QA-006 | all | MUST check actual diff against Issue allowlist, `git diff --check`, tracked/untracked secrets/build output and link validation before PR | STATIC | STOP |
| QA-007 | all | MUST NOT claim Full CERT C compliance from selected checks; state exactly which rule/checker was applied | STATIC/HUMAN | FIX |
| QA-008 | all | MUST obtain human technical review for RF, SPI/ISR/timer, security and versioned interface changes; automated lint/auditor is not signature | HUMAN | STOP |
## 12. Blocked decisions — never resolve in coding standard
| Decision | Current source status | Agent behavior |
|---|---|---|
| D01/D11 | BLOCKED G2 | No production frame layout, key/nonce/MIC/replay/epoch design or fake golden bytes |
| D02/D04/D05 | CANDIDATE / needs G1/G2/G3 | No numeric ToA/jitter/drift/guard/superframe/activation horizon guarantee |
| D03 | BLOCKED G1 | No approved Vietnamese RF frequency, power, duty, ERP or TX authority inferred from examples |
| D06/D07/D09/D10/D12 | PROPOSED / some BLOCKED | No implicit MQTT topic aliases, sensor scaling, alert mapping or infinite-buffer promise |
| D08 | MQTT 5.0 OWNER_ACCEPTED, cross-team PENDING | Preserve chosen version; do not infer all detailed MQTT rules approved/implemented |
| D13 | BLOCKED Security | No arbitrary production REST/WSS credential/token lifecycle scheme |
| G0 | NOT_VERIFIED pending human approval | RTM/ADR approval and firmware standard approval are independent; never self-mark a Gate PASS |

**Design authority boundaries:** `contracts/radio-mac/`, `contracts/mqtt/`, `contracts/api/` and `backend-go/migrations/` own their respective payloads and data contracts. A firmware Issue authorizing `firmware/**` does **not** authorize modifying those paths. `SEC-005` and `SYS-003` in RTM open items are proposed future coverage IDs, not approved requirements or ready-made implementation specifications.
## 13. Deterministic agent checklist (required PR evidence)
### Preflight
**Pre-edit report:** `ISSUE_URL`, `BASE_SHA`, `BRANCH`, `ISSUE_ALLOWED_PATHS`, `APPLICABLE_RULE_IDS`, `RULE_APPROVAL_STATUS`, `CONTRACT_CONFLICTS`, `BLOCKED_DECISIONS`, `TEST_PLAN`.
### Verification selection
| Change kind | Minimum review/check (as permitted by Issue) | Explicitly NOT implied |
|---|---|---|
| Formatting/header | diff/formatter, compile of affected C/header if actually available | Behavior/HIL |
| Memory/queue/RTOS | static review, capacity/overflow/fault tests, actual target build | Latency/soak PASS |
| SX1276 driver/IRQ/SPI | v6.1 API review, register/datasheet review, fault HIL traces | RF compliance |
| Radio MAC | approved contract, bounds/negative cases, C↔Go golden vectors after crypto freeze | Security proof from CRC |
| TDMA scheduling | static validator, simulation then measured ToA/IRQ/drift/guard and recovery HIL | Numeric guarantees from planner |
| MQTT/API boundary | reviewed schema/version, producer/consumer integration, ACL/replay/expiry | PUBACK = application ACK |
### PR result contract
**Final task/review report:** `TASK_ID`, `ISSUE_URL`, `BASE_SHA`, `HEAD_SHA`, `BRANCH`, `CHANGED_PATHS`, `SCOPE_CHECK`, `RULE_IDS_CONSULTED`, `RULE_IDS_APPLIED`, `CONFLICTS_OR_EXCEPTIONS`, `BLOCKED_DECISIONS`, `TOOLCHAIN_VERSION`, `TEST_COMMANDS`, `TESTS_RUN`, `NOT_RUN`, `KNOWN_LIMITATIONS`, `EVIDENCE_STATUS`, `EVIDENCE_URLS`, `REVIEWERS_REQUIRED`, `PR_URL`, `FINAL_STATUS`. Values must be truthful. Relevant G0–G6 gates remain `NOT_VERIFIED` absent their distinct evidence.
## 14. AI agent conformance evaluation (test specification; NOT_EXECUTED)
AI agent conformance evaluation scenarios (CASE-01..12) are maintained in [agent-conformance-scenarios.md](../../verification/agent-conformance-scenarios.md) (`NOT_EXECUTED`). AI Coding Workers must not load that file during normal implementation tasks.
## 15. Source/provenance and migration matrix
- [Cold source traceability](../../audits/firmware/C_STANDARD_SOURCE_TRACEABILITY.md) maps upstream IDs to operational v2 domains. Upstream `docs/C_CODING_STANDARDS.md` at `khanhpn308/esp32e_sx1768-915Mhz@2af2bd2a99234b15f59848f4bdd0b1e920c2dcd5`; SHA-256 `70fc06ec5f21e21725f0227238ed3ab258e21b113b95f9ef481332d54715c5de`.
- GOV/ARCH/SEC/MAC/TDMA/QA use `AGENTS.md`, approved `docs/requirements/`, `docs/adr/`, `contracts/` and `docs/verification/acceptance-gates.md` according to their individual approval status. No standard grants authority to resolve blocked contracts.
- C/MEM/ERR/RTOS/RAD use source traceability, exact ESP-IDF v6.1 APIs and manufacturer documents. [ESP-IDF v6.1 ESP32 esp_timer](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-reference/system/esp_timer.html) distinguishes task and ISR dispatch. Verify API, board and silicon revision before adopting assumptions.
- Hardware sources: Semtech `SX1276_Datasheet.pdf`; Espressif `esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf`. Demo values do not approve RF profiles, pins, timing or crypto.

| Upstream v1 domain | v2 implementation | Disposition boundary |
|---|---|---|
| FMT, NAM, API, TYP | C-001..020; ARCH | Preserve style/interface intent, amend namespace/header/CMake and remove demo fixed-wire assumptions |
| MEM, ERR | MEM-001..008; ERR-001..007 | Preserve bounded resource/error behavior; reject fixed demo 256B stack and unvalidated DMA assumptions |
| RTOS | RTOS-001..010 | Single Radio Owner; accurate v6.1 timer contexts; measurement required for timing |
| RAD | RAD-001..009 | Driver rules only; exact registers, PHY and hardware profiles owned by datasheet/G1 |
| PRO | SEC-001..008; MAC-001..007 | Security and parser rules; no 8-byte header/CRC-only production codec |
| HW | GOV-004; RAD-005/007 | Hardware/GPIO/power facts relocated to board revision and legal/RF evidence |
| DOC, QA | QA-001..008; §13/14 | Distinguish proof types, explicit claims and agent conformance |
