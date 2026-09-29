/**
 * Parse a user-entered timecode into seconds.
 *
 * Accepts `HH:MM:SS`, `MM:SS`, plain seconds, and optional fractional seconds
 * (`1:02.5`). Returns `null` for anything else so callers can show a clear error.
 */
export function parseTimecode(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;

  const parts = trimmed.split(":");
  if (parts.length > 3) return null;

  const numbers = parts.map((part, index) => {
    const isLast = index === parts.length - 1;
    const pattern = isLast ? /^\d+(\.\d+)?$/ : /^\d+$/;
    if (!pattern.test(part)) return null;
    const parsed = Number(part);
    if (!isLast && parsed >= 60 && parts.length > 1 && index > 0) return null;
    return parsed;
  });
  if (numbers.some((part) => part === null)) return null;

  const values = numbers as number[];
  if (values.length > 1) {
    const seconds = values[values.length - 1];
    if (seconds >= 60) return null;
  }

  return values.reduce((total, part) => total * 60 + part, 0);
}

/** Format seconds as `HH:MM:SS`, dropping the hour block when it is zero. */
export function formatTimecode(totalSeconds: number): string {
  const safe = Math.max(0, totalSeconds);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = Math.floor(safe % 60);
  const mmss = `${minutes.toString().padStart(2, "0")}:${seconds
    .toString()
    .padStart(2, "0")}`;
  return hours > 0 ? `${hours.toString().padStart(2, "0")}:${mmss}` : mmss;
}
