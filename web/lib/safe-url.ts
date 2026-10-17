/** Artifact URLs are data from the API, not trusted navigation instructions. */
export function safeArtifactUrl(raw: unknown): string | undefined {
  if (typeof raw !== "string" || !raw || raw !== raw.trim() || /[\u0000-\u0020\u007f\\]/.test(raw)) return undefined;
  if (raw.startsWith("/") && !raw.startsWith("//")) return raw;
  try {
    const url = new URL(raw);
    if ((url.protocol === "https:" || url.protocol === "http:") && !url.username && !url.password) return raw;
  } catch {
    // Reject malformed URLs and active schemes such as javascript:, data:, file:.
  }
  return undefined;
}
