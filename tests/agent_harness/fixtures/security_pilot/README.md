# Supervised Harness Security Pilot Fixture

This directory contains a harmless fixture created under the supervised Gemini
Worker + Gemini Auditor pilot for GitHub Issue #47.

- **Role Separation**: The Gemini Worker and Gemini Auditor operate in separate,
  independent Antigravity (`agy`) CLI sessions without shared conversation state.
- **Scope & Verification**: Firmware, RF transmission, and HIL (Hardware-in-the-Loop)
  are completely untouched and remain `NOT_VERIFIED`.
- **Harmlessness**: This fixture introduces no executable logic, credentials,
  network calls, or modifications to wire protocol contracts.
