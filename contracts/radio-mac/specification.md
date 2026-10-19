# Custom LoRa P2P Radio MAC — CONTRACT DRAFT 0

**UNAPPROVED**. This is not LoRaWAN; LoRa physical modem settings alone do not define this MAC.

## Proposed packet model
- Preamble and hardware PHY CRC are configured at SX1276; a proposed binary MAC header and payload are transported through FIFO.
- Prior planning document suggested an 8-byte header: MAGIC, VER_TYPE, FLAGS, SRC_ID, DST_ID, SCHED_VER, SEQ_NUM, PAY_LEN, optional app CRC16. **This is not frozen.** It does not carry a cryptographic authentication tag, unique network/boot nonce or a sufficiently wide replay window.
- Data frames must authenticate relevant control and preserve nonce uniqueness after power loss; design and vet the authenticated framing before production implementation.
- Proposed messages: BEACON, DATA, ALERT, ACK, SCHEDULE, JOIN/RECOVERY and DOWNLINK. Exact byte allocations/endian/priority levels are TBD.
- Keep protocol version in frame; define reserved bits, maximum body and backward/forward compatibility.
- Use explicit serialization/deserialization with bounds checking, never raw packed C structs on wire.

## TDMA state and safety invariants
- Gateway single SX1276 is half-duplex; cannot receive simultaneous while beacon/ACK transmission is active.
- Schedule change is staged then announced then activated on a safe future boundary; define Node acknowledgement/missed announcement/rollback.
- Guard time derives from measured oscillator drift, IRQ timestamp paths, processing variance and radio turnaround; never assume perfect synchrony.
- Any CAD/backoff scheme is best effort (preamble detection), not collision-free arbitration.
- Local radio TX limits count data, beacons, ACK, retries and emergency transmissions. Emergency operation is not an exemption from legal RF limits.

## Verification to freeze v1.0
1. Choose and review authenticated frame format and network/session IDs.
2. Supply byte-level golden vectors: valid, truncated, tampered, wrong version, replay, wrap-around, malformed length.
3. Cross-language vectors C/Go plus measured airtime and HIL timing budgets.
4. Log ADR and PASS of appropriate G1/G2 security checks.

See `test-vectors/README.md`. No production RF encoder exists in this scaffold.
