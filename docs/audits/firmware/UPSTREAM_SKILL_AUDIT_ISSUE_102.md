# Upstream skill audit — Issue #102 (Cold Audit Archive)

> Current archival content lifecycle: `OWNER_APPROVED_FROZEN` (Issue #108, 2026-10-28). The historical observations and review dispositions below retain their original dates and scope; this freeze does not imply technical approval or verification.

Provenance evidence only, not Worker instructions. U1/U2/U3 remain `PENDING_LICENSE`; U4/U5 are attributed workflow-idea adaptations. [Hot Playbook](../../development/firmware/ESP32_LORA_ENGINEERING_PLAYBOOK.md#task-index).

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
