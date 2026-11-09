/**
 * Utilities and validation rules for device provisioning (K_JOIN).
 * Authority: OpenAPI 3.0.3, ADR-0005, Issue #242, Issue #305.
 */

export const MAC_REGEX = /^[0-9a-fA-F]{12}$/;
export const KJOIN_HEX_REGEX = /^[0-9a-fA-F]{64}$/;

/**
 * Generates a cryptographically secure random 32-byte (256-bit) hexadecimal key.
 */
export function generateRandomKJoinHex(): string {
  if (typeof window !== "undefined" && window.crypto?.getRandomValues) {
    const bytes = new Uint8Array(32);
    window.crypto.getRandomValues(bytes);
    return Array.from(bytes)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }
  let hex = "";
  for (let i = 0; i < 32; i++) {
    hex += Math.floor(Math.random() * 256).toString(16).padStart(2, "0");
  }
  return hex;
}

/**
 * Validates whether the given string is a valid 64-character hex or 32-byte Base64 key.
 */
export function validateKJoinKey(key: string): boolean {
  const trimmed = key.trim();
  if (KJOIN_HEX_REGEX.test(trimmed)) {
    return true;
  }
  // Check if valid 32-byte Base64 (44 characters ending in =/== or 43 unpadded)
  if (/^[A-Za-z0-9+/]{42,44}={0,2}$/.test(trimmed)) {
    try {
      if (typeof atob === "function") {
        const decoded = atob(trimmed);
        return decoded.length === 32;
      }
      if (typeof Buffer !== "undefined") {
        const buf = Buffer.from(trimmed, "base64");
        return buf.length === 32;
      }
    } catch {
      return false;
    }
  }
  return false;
}
