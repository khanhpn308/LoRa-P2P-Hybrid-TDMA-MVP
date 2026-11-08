# node_tdma_client

Sensor Node V2 static TDMA Slot Client and event transmission engine.

## Features
- **Beacon Synchronization:** Synchronizes superframe timing to Gateway Beacon broadcasts (`DOWN_SYNC_BEACON` 0x43).
- **Assigned DATA Slot Transmission:** Wakes and transmits queued events during dedicated node slot window with strict guard intervals.
- **Node Cryptographic Backend:** Beacon HMAC verification and AES-128-CCM-8 payload encryption/decryption (`node_crypto`).
- **In-Slot ACK Qualification:** Waits for `DOWN_EVENT_ACK` (0x42) and retires events from `node_event_fifo` on successful ACK.
- **Fail-Closed Drift & Loss Handling:** Automatically shifts to disconnected fallback on consecutive beacon loss.
