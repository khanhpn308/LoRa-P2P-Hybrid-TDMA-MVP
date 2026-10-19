# lora_mac — design pending

Shared bounded encode/decode logic for Node and Gateway. The radio MAC is currently DRAFT, not frozen at 8 bytes; read `contracts/radio-mac/specification.md`. Implement authentication, per-session replay handling, length checks, versioning and golden vectors before claiming a production radio protocol.
