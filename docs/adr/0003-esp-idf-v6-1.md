# ADR-0003: ESP-IDF v6.1 baseline for ESP32 + SX1276

- **Status:** APPROVED BY OWNER, 2026-10-22. Build/HIL/RF evidence remains NOT_VERIFIED until completed.
- **Scope / linked Issue:** #30, owner-approved monorepo-wide ESP-IDF baseline migration.
- **Context:** Experimental ESP32/SX1276 firmware used v6.1. Monorepo Gateway/Node CI used floating `release-v5.4`, inconsistent with local builds.
- **Decision:** All firmware development, Gateway CI, Node CI and AI Coding Harness use **ESP-IDF `v6.1`**, defined once in `firmware/esp-idf-version.txt`. CI passes this exact tag to `espressif/esp-idf-ci-action@v1`. The Host Toolchain Resolver reads the same baseline, checks an installed `espressif/idf:v6.1` image identity, and verifies `idf.py --version` reports exactly `ESP-IDF v6.1`.
- **Prohibited substitutions:** floating `latest`, `release-v6.1`, prereleases such as `v6.1-rc1`, or an unreviewed patch `v6.1.0`. Version updates require a new review/ADR amendment.
- **Unchanged:** ESP32 target, SX1276 hardware, LoRa P2P, custom MAC/Hybrid TDMA, GPIO/pinout, RF configuration and all interfaces/contracts.
- **Consequences:** Driver import may need API adaptation from earlier sources; follow ESP-IDF v6.1 API and migration guides. Never treat compile PASS as evidence of radio correctness, regulatory compliance or TDMA timing.
- **Verification:** Require Gateway/Node build logs on the actual PR commit, source scan for mismatched pins, unit/contract tests, human driver/ISR review and HIL/RF measurement as appropriate. No build success assumed in advance.
- **References:** https://github.com/espressif/esp-idf/releases/tag/v6.1 ; https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/api-guides/tools/idf-docker-image.html
