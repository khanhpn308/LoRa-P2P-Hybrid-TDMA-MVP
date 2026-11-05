# ADR 0004: Theoretical LoRa Time-on-Air and Hybrid TDMA Guard Time Budget Model

## Status
**PROPOSED / THEORETICAL_MODEL** (Owner decision boundary: Software/theoretical model defined in Issue #11; physical bench measurements, conducted RF validation, and numerical Guard Time sign-off reserved for Issue #169).

## Context & Problem Statement
The MVP V1 architecture ([ADR-0001](0001-hybrid-tdma.md)) employs a custom LoRa P2P Hybrid TDMA protocol between ESP32-WROOM-32E nodes and a Gateway using the Semtech SX1276 transceiver. The network operates strictly without a LoRaWAN stack.

The Gateway coordinates local TDMA execution. To avoid on-air frame collisions in half-duplex operation, slots must account for:
1. Physical LoRa Time-on-Air (ToA) for variable uplink and acknowledgment payload sizes.
2. Transceiver mode transitions (e.g., Standby $\to$ RX, TX $\to$ RX).
3. Monotonic oscillator drift between uncalibrated quartz crystals across holdover intervals.
4. FreeRTOS task scheduling uncertainty and interrupt dispatch latencies.
5. Propagation delay over target operational range (up to 5–10 km).

Previously, arbitrary numerical constants (such as an unverified 25 ms guard or 400 ms slot) were noted as placeholders. Hardcoding such constants without mathematical modeling or measurement evidence violates architectural integrity and risks packet loss or unrecoverable frame collision.

## Decision

### 1. Authoritative Mathematical Formulation for SX1276 LoRa ToA
Adopt the official Semtech SX1276 airtime equations (Datasheet Rev 7, Section 4.1.1.5–4.1.1.7) as the single theoretical airtime model:

$$T_s = \frac{2^{SF}}{BW}$$

$$T_{preamble} = (N_{preamble} + 4.25) \times T_s$$

$$N_{payload} = 8 + \max\left( \left\lceil \frac{8 \cdot PL - 4 \cdot SF + 28 + 16 \cdot CRC - 20 \cdot H}{4 \cdot (SF - 2 \cdot DE)} \right\rceil \cdot (CR + 4),\, 0 \right)$$

$$T_{packet} = T_{preamble} + N_{payload} \times T_s$$

Where:
- $SF \in [6, 12]$ (MVP V1 uses $SF=7$, test fallback $SF=8$).
- $BW = 125,000\text{ Hz}$ (VN920 channel plan).
- $CR = 1$ ($4/5$ coding rate).
- $H = 0$ (Explicit header mode).
- $CRC = 1$ (Payload CRC enabled).
- $DE = 1$ if $T_s > 16\text{ ms}$, else $0$ (Low Data Rate Optimization).
- $PL \in [0, 255]$ bytes (MVP V1 matrix: 12, 24, 32, 48 bytes).

All software outputs from this equation must be labeled `CALCULATED`.

### 2. Conservative, Non-Double-Counted Guard Time Budget
Adopt a symbolic, non-double-counted Guard Time budget:

$$T_{guard} = \left( T_{drift} + T_{sync\_uncertainty} + T_{task\_jitter} + T_{rx\_turnaround} + T_{prop} \right) \times M_{safety}$$

With parameters defined as:
1. **Oscillator Relative Drift ($T_{drift}$)**:
   $$T_{drift} = 2 \times \text{PPM}_{max} \times T_{sync\_window}$$
   For a standard $\pm 20\text{ PPM}$ quartz crystal:
   - Over a fast $10\text{ s}$ beacon interval: $T_{drift} = 2 \times 20 \times 10^{-6} \times 10\text{ s} = 400\text{ µs}$.
   - Over the $300\text{ s}$ maintenance target interval: $T_{drift} = 2 \times 20 \times 10^{-6} \times 300\text{ s} = 12,000\text{ µs} = 12\text{ ms}$.
2. **Synchronization Uncertainty ($T_{sync\_uncertainty}$)**:
   Timestamp latching and interrupt latency when receiving the SYNC Beacon (modeled at $\le 25\text{ µs}$).
3. **Task & ISR Scheduling Jitter ($T_{task\_jitter}$)**:
   FreeRTOS timer and task dispatch latency on ESP32 Dual Core (modeled at $\le 100\text{ µs}$).
4. **Radio RX Readiness Turnaround ($T_{rx\_turnaround}$)**:
   Transceiver transition from Standby to RX mode, including PLL lock time (SX1276 datasheet: $\sim 60\text{ µs}$).
5. **Propagation Delay ($T_{prop}$)**:
   $T_{prop} = \frac{d}{c} \approx 3.336\text{ µs/km} \times \text{Distance (km)}$. For $5\text{ km}$, $T_{prop} \approx 16.7\text{ µs}$.
6. **Engineering Safety Margin ($M_{safety}$)**:
   Conservative multiplicative factor ($M_{safety} = 1.25$, i.e. 25% slack).

### 3. Half-Duplex Slot Formulation
For an Uplink DATA slot with slotted Gateway ACK in the same slot:

$$T_{slot} = \text{ToA}_{uplink} + \text{ToA}_{ack} + T_{guard}$$

### 4. Strict Evidence Classification
To prevent false verification claims, timing metrics must be strictly classified into five orthogonal categories:
1. `CALCULATED_TOA`: Theoretical model equations.
2. `HOST_SYNTHETIC`: Deterministic regression fixtures for host tooling.
3. `SOFTWARE_TIMESTAMP`: ESP32 `esp_timer_get_time()` monotonic microsecond latches.
4. `HARDWARE_CAPTURE`: External logic analyzer GPIO pulse captures.
5. `EXTERNAL_RF_MEASURED`: Calibrated bench oscilloscope / RF spectrum analyzer captures.

No software timestamp or synthetic fixture may be represented as measured RF airtime.

### 5. Fail-Closed RF Safety Policy
Firmware timing harnesses must boot with RF transmission disabled (`rf_tx_enabled = false`). Transmission attempts fail closed unless explicit PA path verification and regulatory power limits are confirmed.

## Alternatives Considered
- **Fixed Numerical 25 ms Guard**: Rejected. Unsubstantiated by crystal tolerance or holdover calculations; overly conservative for 10 s intervals yet inadequate if holdover extends without resync.
- **Pure Oscilloscope Measurement without Software Instrumentation**: Rejected. External RF captures cannot observe task dispatch jitter, internal FreeRTOS queue delays, or ring buffer overflows.

## Consequences & Division of Responsibilities
- **Issue #11 Deliverable (Agent)**: Theoretical ToA calculator, profile matrix, test-only firmware harness source, host logger, synthetic fixtures, statistical analyzer, and parameterized feasibility calculator.
- **Issue #169 Handoff (Hardware Owner)**: Bench test execution with calibrated oscilloscope, PA path verification, physical temperature drift measurement, sample count $\ge 1000$, and numerical production Guard Time sign-off.
