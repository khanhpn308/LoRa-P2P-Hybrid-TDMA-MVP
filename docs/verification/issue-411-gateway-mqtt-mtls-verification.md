# Issue #411 Verification — Gateway MQTT 5.0 over mTLS & NVS Provisioning

- **Issue:** `#411` (`[FW][Security] Triển khai kết nối MQTT 5.0 over mTLS trên Gateway firmware`)
- **Base Commit:** `e8187e655b3e8595d699a32f7d93e610e940de29`
- **Branch:** `feature/411-gateway-mqtt-mtls`
- **Toolchain:** `espressif/idf@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c` (ESP-IDF v6.1), `gcc` (`-std=c11 -Wall -Wextra -Werror -pedantic`), Python 3.12.3
- **Status:** `PARTIAL / DONE_FOR_REVIEW` (`HIL / Mosquitto live run: NOT_VERIFIED`, `HUMAN_SECURITY_REVIEW: PENDING`)

## 1. Summary of Changes

1. **Broker URI Resolution & Removal of Hardcoded IP (`gateway_mqtt.h`, `gateway_mqtt.c`, `Kconfig.projbuild`, `sdkconfig.defaults`, `gateway_app.c`)**
   - Added `CONFIG_GATEWAY_MQTT_TLS_ENABLED` (`default y` in `Kconfig.projbuild` and `=y` in `sdkconfig.defaults`).
   - Added `gateway_mqtt_resolve_broker_uri()` and `gateway_mqtt_is_tls_uri()`:
     - Prioritizes non-empty `CONFIG_GATEWAY_BROKER_URI` (rejecting cleartext `mqtt://` override when `CONFIG_GATEWAY_MQTT_TLS_ENABLED=y`).
     - When `CONFIG_GATEWAY_BROKER_URI` is empty, constructs `<scheme>://<host>:<port>` from `CONFIG_GATEWAY_BROKER_HOST` and `CONFIG_GATEWAY_BROKER_PORT`, using `mqtts://` when TLS is enabled or `port == 8883`, and `mqtt://` only when TLS is explicitly disabled (`CONFIG_GATEWAY_MQTT_TLS_ENABLED=n`) and `port != 8883`.
   - Removed the hardcoded `"mqtts://192.168.1.10:8883"` fallback in `gateway_mqtt_init()`; empty or unsupported broker URIs now fail closed (`ESP_ERR_INVALID_ARG`).

2. **mTLS NVS Loading, Gitignored Embed Fallback & Fail-Closed Guards (`gateway_transport.h`, `gateway_transport.c`, `gateway_mqtt.c`, `gateway_app.c`, `gateway_app/CMakeLists.txt`)**
   - Added `gateway_mqtt_validate_pem()` verifying non-NULL, non-empty, NUL-terminated PEM bounds (`<= 4096B`), BEGIN/END markers, and certificate vs private key header separation.
   - Added `gateway_transport_load_tls_certs_from_nvs()` reading `gateway_id`, `ca_cert`, `client_cert`, `client_key` from NVS namespace `nvs_tls`, enforcing `expected_gateway_id` match and zeroizing all caller buffers via `mbedtls_platform_zeroize` on any failure.
   - Updated `gateway_app.c` to resolve the broker URI, load mTLS credentials from NVS `nvs_tls` into static lifetime buffers (`s_tls_ca_cert`, `s_tls_client_cert`, `s_tls_client_key`), fall back to gitignored `firmware/gateway_master/secrets/{ca.crt,client.crt,client.key}` only when `nvs_tls` returns `ESP_ERR_NVS_NOT_FOUND` and `GATEWAY_HAS_EMBEDDED_TLS_CERTS=1` is compiled in, and otherwise fail closed without calling `gateway_transport_init()` or downgrading to `mqtt://`.
   - On `ESP_PLATFORM`, `gateway_mqtt_init()` parses both `broker_ca_cert` and `client_cert` via `mbedtls_x509_crt_parse()` and verifies that the client certificate Subject CN matches `gateway_id` (`use_identity_as_username true` per `deploy/mosquitto/tls.conf`).
   - Reordered `gateway_transport_init()` so `gateway_mqtt_init()` validates credentials fail-closed before creating FreeRTOS tasks/queues, and cleans up resources if `gateway_wifi_init()` fails.

3. **Gateway mTLS NVS Provisioning Tool (`tools/provisioning/nvs_generator.py`, `tools/provisioning/provision_gateway.py`)**
   - Extended `NVSV2PartitionWriter` with multi-page ESP-IDF v6.1 V2 blob synthesis (`synthesize_gateway_tls_partition()`), verified byte-for-byte identical against Espressif `esp_idf_nvs_partition_gen`.
   - Added `tools/provisioning/provision_gateway.py` supporting PEM validation, OpenSSL Subject CN vs `--gateway-id` check, cert/key public-key match check, CA chain verification, `esptool.py` flashing to `0x9000`, `--dry-run`, `--output-bin` (`0600` perms), memory zeroization, and secure temp-file wiping.

4. **Unit Tests & Documentation (`tests/unit/`, `docs/deploy/`)**
   - Updated `tests/unit/test_gateway_transport.c` and `tests/unit/test_gateway_transport.py` (linking `mock_nvs.c`) with URI resolution, downgrade rejection, fail-closed missing/malformed cert checks, and NVS `nvs_tls` loading/zeroization tests.
   - Added `tests/unit/test_provision_gateway_tool.py` covering multi-page NVS synthesis, Espressif byte-parity, CLI `--dry-run`, OpenSSL CN/key mismatch rejection, and secret masking.
   - Added `docs/deploy/gateway-mtls-provisioning.md`.

## 2. Observed Verification Results

| Check | Command | Result | Notes |
|---|---|---|---|
| Gateway Transport C11 unit tests | `python3 -m unittest discover -s tests/unit -p "test_gateway_transport.py" -v` | **PASS** (1/1, exit 0) | Compiled with `-Wall -Wextra -Werror -pedantic -std=c11`; all 10 C test functions passed. |
| Gateway NVS provisioning unit tests | `python3 -m unittest discover -s tests/unit -p "test_provision_gateway_tool.py" -v` | **PASS** (9/9, exit 0) | Includes byte-for-byte parity check against installed `esp_idf_nvs_partition_gen` and OpenSSL CN/key checks. |
| Node NVS provisioning regression tests | `python3 -m unittest discover -s tests/unit -p "test_provision_node_tool.py" -v` | **PASS** (24/24, exit 0) | Confirms `nvs_generator.py` backward compatibility. |
| ESP-IDF v6.1 disposable-copy build (NVS primary) | `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v /tmp/idf-build-411:/workspace -w /workspace/firmware/gateway_master espressif/idf@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c idf.py build` | **PASS** (exit 0) | `gateway_master.bin` size `0xf7e80` bytes (`0x8180` bytes / 3% free in `0x100000` app partition); 0 warnings/errors in modified components. |
| ESP-IDF v6.1 disposable-copy build (embedded fallback) | `idf.py reconfigure build` in disposable copy with synthetic `secrets/{ca.crt,client.crt,client.key}` | **PASS** (exit 0) | Verifies `GATEWAY_HAS_EMBEDDED_TLS_CERTS=1` and `target_add_binary_data` linkage. |
| Diff hygiene | `git diff --check e8187e655b3e8595d699a32f7d93e610e940de29` | **PASS** (exit 0) | Clean whitespace and no conflict markers. |
| Secret scan (Issue #411 files) | `verify_no_secrets.forbidden_path` & `contains_secret` across all 15 changed/added files | **PASS** (`CLEAN`) | Full-repo `verify_no_secrets.py` exits non-zero only on pre-existing baseline matches in untouched `backend-go/internal/auth/service_test.go`, `clients/web-dashboard/*`, and `scripts/agent_harness/quality_gates.py`. |

## 3. Remaining `NOT_VERIFIED` & Human Gates

- **HIL / Integration Test on ESP32-WROOM-32E (`flag:needs-hil-test`):** `NOT_VERIFIED` — physical ESP32 flashing, live `mqtts://<SERVER_IP>:8883` handshake against Mosquitto `mqtt-tls`, UART logs (`MQTT_EVENT_CONNECTED`, downlink subscriptions, `uplink/status`), and negative hardware tests (wrong CA / missing NVS key) require bench hardware and were not executed in this session.
- **Human Security Review (`ai:human-audit-req`):** `PENDING` — owner/security reviewer sign-off is required before merge on NVS key handling, `esp_mqtt_client_config_t` TLS verification settings, and provisioning tooling.
