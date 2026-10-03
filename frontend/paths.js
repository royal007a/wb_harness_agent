"use strict";
(() => {
  // Derive the deployment prefix from our own same-origin script, not the
  // current route (nested connector routes must behave exactly like home).
  const script = new URL(document.currentScript.src);
  const suffix = "/static/paths.js";
  const prefix = script.pathname.slice(0, -suffix.length);
  if (script.origin !== location.origin || !script.pathname.endsWith(suffix) || !["", "/harness"].includes(prefix)) {
    throw new Error("Unsupported Harness mount point");
  }
  function url(path) {
    if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//") || path.includes("\\")) {
      throw new Error("Expected a same-origin absolute application path");
    }
    const resolved = new URL(prefix + path, location.origin);
    if (resolved.origin !== location.origin || (prefix && !resolved.pathname.startsWith(prefix + "/"))) {
      throw new Error("Application path escapes its mount point");
    }
    return resolved.pathname + resolved.search + resolved.hash;
  }
  function requestId() {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  window.HarnessURLs = Object.freeze({ url, requestId });
})();
