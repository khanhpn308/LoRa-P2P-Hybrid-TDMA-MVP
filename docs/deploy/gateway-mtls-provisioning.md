# Hướng dẫn cấp phát & nạp chứng chỉ mTLS cho ESP32 Gateway Master

Tài liệu này hướng dẫn quy trình cấp phát chứng chỉ X.509, đồng bộ danh tính ACL/CN và nạp khóa mTLS vào phân vùng NVS của ESP32-WROOM-32E (`firmware/gateway_master/`) để kết nối an toàn tới Mosquitto `mqtt-tls:8883` (MQTT 5.0 over TLS 1.2+, xác thực hai chiều).

> [!IMPORTANT]
> - **Fail-closed mặc định:** Khi `CONFIG_GATEWAY_MQTT_TLS_ENABLED=y` (mặc định) hoặc port là `8883` hoặc URI là `mqtts://`, firmware **bắt buộc** phải nạp đủ `ca_cert`, `client_cert`, `client_key` hợp lệ và khớp `CONFIG_GATEWAY_ID`. Nếu thiếu hoặc hỏng, Gateway sẽ từ chối kết nối MQTT thay vì hạ cấp về `mqtt://`.
> - **Không commit khóa/chứng chỉ vào Git:** Toàn bộ khóa riêng và chứng chỉ thử nghiệm/triển khai phải lưu ở thư mục đã ignore (`deploy/secrets/` hoặc `firmware/gateway_master/secrets/`).

---

## 1. Chuẩn bị chứng chỉ mTLS (CA, Broker SAN, Gateway CN)

1. Kiểm tra `deploy/mosquitto/tls.conf` và `deploy/mosquitto/acl`:
   - `require_certificate true`
   - `use_identity_as_username true` (Mosquitto dùng **Subject CN** của chứng chỉ client làm username cho ACL)
   - `tls_version tlsv1.2`
   - Các user mẫu trong `deploy/mosquitto/acl` gồm `gw-a`, `gw-b`, `backend`.
2. Đảm bảo chứng chỉ server (`deploy/secrets/broker/server.crt`) có `subjectAltName` chứa **IP LAN hoặc tên miền** mà ESP32 Gateway thực tế dùng để kết nối (ví dụ `IP:192.168.1.10`), bên cạnh `DNS:mqtt-tls,DNS:localhost,IP:127.0.0.1`.
3. Cấp cặp chứng chỉ riêng cho từng Gateway vật lý với `/CN=<GATEWAY_ID>` (ví dụ `gw-a`, `gw-b`) trong thư mục gitignored `deploy/secrets/`:

```bash
umask 077
mkdir -p deploy/secrets/pki deploy/secrets/broker deploy/secrets/clients

CERT_DAYS=365
SERVER_LAN_IP="192.168.1.10"   # Thay bằng IP thực của máy chạy Mosquitto mqtt-tls

# 1) Tạo Root CA nếu chưa có
openssl req -x509 -newkey rsa:2048 -nodes -days "${CERT_DAYS}" \
  -subj "/CN=lora-mqtt-ca" \
  -keyout deploy/secrets/pki/ca.key \
  -out deploy/secrets/broker/ca.crt

# 2) Cấp server.crt cho Mosquitto với SAN gồm DNS nội bộ và IP LAN cho ESP32
openssl req -new -newkey rsa:2048 -nodes \
  -subj "/CN=mqtt-tls" \
  -addext "subjectAltName=DNS:mqtt-tls,DNS:localhost,IP:127.0.0.1,IP:${SERVER_LAN_IP}" \
  -addext "extendedKeyUsage=serverAuth" \
  -keyout deploy/secrets/broker/server.key \
  -out deploy/secrets/pki/server.csr

openssl x509 -req -in deploy/secrets/pki/server.csr -days "${CERT_DAYS}" \
  -CA deploy/secrets/broker/ca.crt -CAkey deploy/secrets/pki/ca.key -CAcreateserial \
  -copy_extensions copy \
  -out deploy/secrets/broker/server.crt

# 3) Cấp chứng chỉ client cho Gateway (ví dụ gw-a; CN phải khớp CONFIG_GATEWAY_ID và ACL)
GW_ID="gw-a"
openssl req -new -newkey rsa:2048 -nodes \
  -subj "/CN=${GW_ID}" \
  -addext "extendedKeyUsage=clientAuth" \
  -keyout "deploy/secrets/clients/${GW_ID}.key" \
  -out "deploy/secrets/pki/${GW_ID}.csr"

openssl x509 -req -in "deploy/secrets/pki/${GW_ID}.csr" -days "${CERT_DAYS}" \
  -CA deploy/secrets/broker/ca.crt -CAkey deploy/secrets/pki/ca.key -CAcreateserial \
  -copy_extensions copy \
  -out "deploy/secrets/clients/${GW_ID}.crt"
```

---

## 2. Cấu hình Kconfig trên `firmware/gateway_master`

Trong `idf.py -C firmware/gateway_master menuconfig` (mục **Gateway Master Configuration**):

| Kconfig | Giá trị khuyến nghị | Ghi chú |
|---|---|---|
| `CONFIG_GATEWAY_ID` | `"gw-a"` | Phải khớp chính xác `/CN=` của `client_cert` và block `user` trong `deploy/mosquitto/acl`. |
| `CONFIG_GATEWAY_BROKER_URI` | `""` (để trống) | Nếu nhập tay (vd `mqtts://192.168.1.10:8883`), URI này được ưu tiên. Khi `CONFIG_GATEWAY_MQTT_TLS_ENABLED=y`, firmware từ chối URI `mqtt://`. |
| `CONFIG_GATEWAY_BROKER_HOST` | `"192.168.1.10"` | Hostname hoặc IP của Mosquitto `mqtt-tls` khi `CONFIG_GATEWAY_BROKER_URI` rỗng. |
| `CONFIG_GATEWAY_BROKER_PORT` | `8883` | Cổng `8883` tự động chọn scheme `mqtts://`. |
| `CONFIG_GATEWAY_MQTT_TLS_ENABLED` | `y` (mặc định) | Chỉ tắt (`n`) khi test opt-in `dev-insecure` (`mqtt://...:1883`) trên mạng cô lập. |

---

## 3. Phương án A (Khuyến nghị): Nạp mTLS vào NVS qua `provision_gateway.py`

Công cụ `tools/provisioning/provision_gateway.py` kiểm tra tính hợp lệ PEM, đối chiếu Subject CN với `--gateway-id`, kiểm tra khóa công khai của `client_cert` khớp `client_key`, kiểm tra chuỗi CA, tổng hợp phân vùng NVS v2 (namespace `nvs_tls` gồm `gateway_id`, `ca_cert`, `client_cert`, `client_key` kết thúc NUL) và nạp vào offset `0x9000` (kích thước `0x6000`):

1. **Chạy thử (`--dry-run`, không cần phần cứng):**
   ```bash
   python3 tools/provisioning/provision_gateway.py \
     --gateway-id gw-a \
     --ca-cert deploy/secrets/broker/ca.crt \
     --client-cert deploy/secrets/clients/gw-a.crt \
     --client-key deploy/secrets/clients/gw-a.key \
     --dry-run
   ```
2. **Nạp lên ESP32-WROOM-32E (chỉ NVS hoặc kèm `gateway_master.bin`):**
   ```bash
   python3 tools/provisioning/provision_gateway.py \
     --gateway-id gw-a \
     --ca-cert deploy/secrets/broker/ca.crt \
     --client-cert deploy/secrets/clients/gw-a.crt \
     --client-key deploy/secrets/clients/gw-a.key \
     --port /dev/ttyUSB0 \
     --firmware-bin firmware/gateway_master/build/gateway_master.bin
   ```
   Tệp NVS tạm được xóa an toàn (`secure_wipe_file`) ngay sau khi nạp xong.

---

## 4. Phương án B (Fallback khi build): Nhúng ngoài Git

Nếu chưa nạp NVS trên thiết bị lab, `gateway_app` hỗ trợ fallback sang chứng chỉ nhúng lúc build từ thư mục gitignored `firmware/gateway_master/secrets/` (chỉ kích hoạt khi `nvs_tls` chưa được nạp, tức `ESP_ERR_NVS_NOT_FOUND`):

```bash
umask 077
mkdir -p firmware/gateway_master/secrets
cp deploy/secrets/broker/ca.crt firmware/gateway_master/secrets/ca.crt
cp deploy/secrets/clients/gw-a.crt firmware/gateway_master/secrets/client.crt
cp deploy/secrets/clients/gw-a.key firmware/gateway_master/secrets/client.key
```

> [!WARNING]
> Phương án B nhúng khóa riêng vào binary firmware (`gateway_master.bin`), do đó tuyệt đối không phân phối binary chứa khóa sản xuất và luôn kiểm tra `git status` + `python3 scripts/verify_no_secrets.py` trước khi commit.

---

## 5. Kiểm tra & Negative Test với Mosquitto `mqtt-tls:8883`

1. Khởi động broker TLS:
   ```bash
   docker compose --env-file .env -f deploy/compose.yaml --profile tls up -d mqtt-tls
   docker compose --env-file .env -f deploy/compose.yaml logs -f mqtt-tls
   ```
2. Quan sát UART của Gateway (`idf.py -C firmware/gateway_master monitor`):
   - Xác nhận log `Loaded mTLS credentials from NVS namespace 'nvs_tls' for gateway 'gw-a'`.
   - Xác nhận `MQTT 5.0 client connected successfully`, subscribe đủ 6 topic `downlink/*` và publish `uplink/status` (`gw-a`).
   - Trên log `mqtt-tls`, xác nhận client kết nối với identity `gw-a` (không phải anonymous).
3. **Negative test (từ chối fail-closed):**
   - Flash firmware lên ESP32 chưa nạp NVS `nvs_tls` và không có `firmware/gateway_master/secrets/`: UART phải báo `Fail-closed: mTLS credentials missing/invalid in NVS 'nvs_tls' ... refusing MQTT connection` và không kết nối `mqtt://`.
   - Nạp sai `ca.crt` hoặc `gw-b.crt` khi `CONFIG_GATEWAY_ID="gw-a"`: từ chối kết nối hoặc bị `verify_x509_certs_and_identity` / TLS handshake chặn.
