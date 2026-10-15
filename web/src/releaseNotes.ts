/** Published notes stay plain text; old sentence-based notes remain readable. */
export function releaseHighlights(notes: string): string[] {
  return notes.split(/\r?\n/u)
    .flatMap(line => line.replace(/^\s*(?:[-*•]|\d+[.)])\s+/u, "").trim().split(/(?<=[.!?])\s+/u))
    .map(line => line.trim()).filter(Boolean).slice(0, 3);
}
