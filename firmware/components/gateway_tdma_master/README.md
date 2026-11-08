# gateway_tdma_master

Gateway Master V2 static TDMA Engine coordinator for Hybrid TDMA MVP.

## Features
- **Master Superframe Epoch:** High-resolution hardware timer (`esp_timer`) drives recurring 10-second reference epochs.
- **Beacon Broadcast:** Emits HMAC-SHA256-128 Beacon frames (`DOWN_SYNC_BEACON` 0x43) under `K_BEACON` with regulatory airtime gating.
- **Dedicated DATA Slots (1..15):** High-precision slot scheduling with half-duplex turnaround guards and continuous RX during usable windows.
- **Cryptographic Operations:** AES-128-CCM-8 decryption and authentication via PSA Crypto dual backend (`gateway_crypto`).
- **Bounded Write-Ahead Log:** In-memory ring buffer WAL (`gateway_wal`) for zero-allocation pre-ACK commit and drop counter tracking.
- **Immediate In-Slot ACK Loop:** Low-latency `DOWN_EVENT_ACK` (0x42) preparation and RF transmission.
- **Maintenance Superframe:** Periodic health and diagnostic slot coordination every 30 superframes.
