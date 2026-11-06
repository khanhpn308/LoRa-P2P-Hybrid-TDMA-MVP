# TDMA Schedule Interface — Đặc tả Vận hành Lịch và Đồng bộ Thời gian

**Revision 0.3.0-draft · Hybrid TDMA & Maintenance Superframe · Issue #127 / Umbrella #125 · Gate G2: NOT_VERIFIED.**

---

## 1. Phân loại lại Profile Cũ P-10S-15 (OBSOLETE_HISTORICAL_BASELINE)

Profile cũ `P-10S-15` (5 subframes $\times$ 2000ms, mỗi subframe chứa 400ms khe tranh chấp PCSS và 3 khe dữ liệu) chính thức được đánh dấu là **`OBSOLETE_HISTORICAL_BASELINE`**.

**Lý do bãi bỏ:**
1. Kiến trúc hệ thống đã chuyển dịch hoàn toàn sang mô hình **Event-Only và Báo động tại chỗ (Local Alarm Autonomy)** theo Quyết định Owner (2026-11-04). Mọi khe tranh chấp PCSS và cơ chế thử lại ngẫu nhiên qua CAD đều bị triệt tiêu khỏi luồng dữ liệu chính.
2. Dữ liệu sự kiện khẩn cấp được báo động bằng còi/đèn tại chỗ ngay lập tức và được truyền tin RF độc quyền trong **Khe Dữ liệu Tĩnh (Static DATA Slot)** của Node.
3. Cơ chế xác nhận gói tin theo lô `ACK_BITMAP` (15 bit) trong Beacon chu kỳ sau bị hủy bỏ; thay vào đó là xác nhận tức thì trong khe `DOWN_EVENT_ACK` (0x42).

---

## 2. Static DATA Superframe — OWNER MVP BASELINE (2026-11-07)

**Architecture:** Local Alarm Autonomy + Event-Only Remote Logging. Node `i` (Gateway-local `NODE_ID=i`, i=1..15) owns implicit DATA position `i` until a signed schedule migration completes. Empty/offline indices remain reserved (no compaction). No periodic application telemetry, Event contention or ACK_BITMAP.

| Parameter | Owner-approved MVP working value |
| --- | ---: |
| `W_MS` — usable Event+ACK window | **500 ms** |
| `G_MS` — leading/trailing guard EACH side | **50 ms** |
| `FULL_DATA_SLOT = W_MS + 2*G_MS` | **600 ms** |
| Reserved Node positions | **15** |
| All 15 reserved positions | **9000 ms**, excluding separate SF overhead |
| DATA Superframe recurrence | Target roughly 10s; exact frame boundary/overhead/versioned profile is separate |

**Do not confuse** 500ms usable `W_MS` with the old **400ms full-slot** example (obsolete and non-normative). A DATA Slot contains the entire workflow:

`Node UP_EVENT TX → Gateway RX/authenticate → Gateway durable WAL/SQLite acceptance → Gateway DOWN_EVENT_ACK TX → Node RX/verify ACK`.

No Backend MQTT/PostgreSQL confirmation is required before RF Event ACK. Missing ACK can mean an Event **or** its ACK was lost; Node preserves the same logical `EVENT_REF` and retries **only in its next own TDMA DATA slot**. Gateway deduplicates and may re-ACK an already durably accepted Event. Re-encrypting changed plaintext under a reused AES-CCM (key,nonce) is prohibited.

**Geometry from authenticated DATA origin, no fictitious Slot0 guard:**

```text
PERIOD = W_MS + 2*G_MS = 600 ms
reserved_start(i) = DATA_ORIGIN + (i-1)*600
usable_start(i)   = reserved_start(i) + 50
usable_end(i)     = usable_start(i) + 500
reserved_end(i)   = reserved_start(i) + 600
```

All Nodes enforce signed generation, own NODE_ID/Slot, valid crypto session, bounded clock error, half-duplex and channel/power before DATA TX. PHY SF7/SF8 ToA, actual WAL latency, ISR jitter, RX/TX turnaround, clock drift and RF legal/airtime bounds require testing; **500ms/50ms are approved implementation inputs, not measured HIL PASS**.

## 3. Join with CAD at any time; Gateway single SX1276 owner

An unjoined Node may begin `UP_JOIN_HELLO 0x45` at **any time**, independent of Maintenance. Run SX1276 CAD on the approved channel/PHY, bounded randomized Backoff if busy, and **maximum three Join retries after the initial transmission**. CAD is only best-effort detection; hidden nodes and preamble timing permit collisions. Pre-Join authenticated Beacon reception is **not required** for initial Join.

When Backend approves Join, Gateway sends its authorized Join response **at the first physically available RF TX opportunity**, not the next Maintenance. The Owner explicitly accepts that Join traffic may collide with/interrupt Event reception or Event ACK, and such an Event Node retries on its next own DATA slot. Gateway cannot RX and TX simultaneously or pretend to abort a physical packet already on-air. Implement bounded radio ownership, handshake timeouts, retry/backoff and no unbounded Join floods.

The Join handshake `UP_JOIN_HELLO 0x45 → DOWN_JOIN_GRANT 0x46 → UP_JOIN_KEY_CONFIRM 0x47 → DOWN_JOIN_FINISH 0x48 → UP_JOIN_READY 0x49` is **not Maintenance-only**. Join READY is **distinct from** `UP_SCHED_READY 0x4C`. Successful Join does not independently activate DATA session/schedule authorization.

## 4. Maintenance — Beacon, Health, Shared Control

Nominal interval between Maintenance opportunities is **~300 seconds**; this is NOT Maintenance duration. The Maintenance contains:
1. `DOWN_SYNC_BEACON 0x43` **32B** (16B information header, 16B HMAC-SHA256-128 tag). Provision 256-bit random `K_BEACON` separately per Gateway out-of-band into authorized Nodes. KEY_ID at header byte12, FLAGS[7:6] reserved=0. HMAC Beacon is time synchronization, **not** Backend schedule authorization.
2. Per-Node scheduled `UP_HEALTH_REPLY 0x44` **21B**. PENDING_COUNT is current FIFO depth, not cumulative dropped Events.
3. Shared Control, normally authenticated management opportunities; `UP_DIAG_METRICS 0x4A` **23B** can TX only when separately allocated in **NORMAL Maintenance**, deferred during migration.
4. During migration only, Shared Control is scheduled for signed PREPARE → deterministic per-Node READY → Backend validation → signed DECISION. No permanently reserved 15 READY slots.

Join remains asynchronous CAD-based even during Maintenance and may collide with these transmissions. There is **no mandatory Protected Join Window**. Gateway controls its *own* radio serialization, not unrelated Join uplink timing. There is **no DATA Beacon Slot0** or per-DATA-SF ACK_BITMAP.

## 5. SCHEDULE_MIGRATION — on-demand, signed, 100% READY

No `3→2→1` Beacon countdown; no Schedule Lease/periodic renewal; an active schedule remains valid until superseded by authorized signed COMMIT. All affected authenticated Node identities are frozen in `AFFECTED_NODE_SET` before starting.

1. **PREPARE:** one Backend-Ed25519-signed **80B Broadcast `DOWN_SCHED_PREPARE`** (candidate type `0x4B`) through Gateway in Maintenance Shared Control. Include generation, common profile, target `W_MS`, Gateway/network context and future `K_TARGET` in the exact signed transaction.
2. **READY:** `UP_SCHED_READY 0x4C` **41B** per affected Node, gateway AES-CCM verified and independently Backend proof verified, only in that Node's assigned READY TDMA position. Distinct from Join READY 0x49.
3. **COMMIT/ABORT:** Backend must verify `VERIFIED_READY_SET == AFFECTED_NODE_SET` (**100%**, including offline still-affected Nodes) before signing COMMIT. Missing/REJECT/forged/collided READY blocks migration; Gateway may defer or issue a valid Backend-signed ABORT. One immutable Backend-signed **80B Broadcast `DOWN_SCHED_DECISION`** (candidate type `0x4D`) cryptographically bound to exact signed PREPARE.
4. **ACTIVATE:** Gateway and Nodes with valid signed COMMIT activate at **common K_TARGET**. A Node that prepared but missed authenticated terminal DECISION must inhibit DATA TX at/after K_TARGET, even across reboot, until trusted reconciliation. No inference from Beacon or MQTT PUBACK.

**Owner-approved READY geometry:**

```text
R_MS = 400 ms usable
G_R_MS = 50 ms leading AND trailing
READY_PERIOD = R_MS + 2*G_R_MS = 500 ms
READY_START(i) = T_READY_BASE + (i-1)*500 + 50
READY_END(i) = READY_START(i) + 400
```

`T_READY_BASE` is from one authenticated Maintenance timing origin, not Node-specific PREPARE reception. For 15 indices, total READY region is **7500 ms**, **only when migrating**; vacant indices stay silent. Backend validation RTT, Beacon, Health, PREPARE/DECISION ToA and all RF guards also need actual Maintenance space. **300s Maintenance recurrence does not mean a 300s Maintenance duration**. A schedule that cannot fit must be deferred, not overlapped with Join/Health/other radio duties.

## 6. Beacon loss, reboot and fail-closed recovery

- **More than 3 consecutive missing Beacons** (`N_MISSED > 3`, fourth miss) triggers a disconnected indication. This is **observability**, not permission to transmit while clock is untrustworthy; DATA TX may inhibit earlier if drift/uncertainty exceeds available guard.
- After **Node reboot:** enter `RX_ONLY / DATA_TX_DISABLED`; await authenticated **Backend-authorized reactivation** with verified session/time/schedule generation. NVS schedule alone does not grant TX. The exact Backend Resume trigger and wire packet are separate implementation design work (a completely RX-only Node cannot autonomously notify Backend that it rebooted).
- No automatic schedule expiry or Schedule Lease. Wrong Beacon key/epoch, replayed SF_SEQ, torn NVS, ambiguous COMMIT or invalid crypto session means no DATA TX until recovered.

## 7. MQTT/Backend lifecycle and evidence

Backend plans signed schedules over MQTT/TLS; Gateway executes local RF timing. MQTT broker PUBACK, Gateway STAGE_ACK and ACTIVE_REPORT are **distinct**; none independently proves every Node got COMMIT. Gateway persists immutable signed decision and correct activation boundary. Duplicated/stale MQTT and RF reports must be idempotently handled.

**MVP implementation status:** Owner approved W500/G50, READY R400/G_R50, Join CAD any time/3 retries, Beacon 32B HMAC, Diagnostic 23B CCM, schedule migration 100% READY and no lease, reboot RX-only. These are sufficient to **begin branch-based implementation**, but cannot establish RF/legal/HIL PASS without actual evidence. Sources: #208, #209, #204, #127, and OPEN_DECISIONS.md.

