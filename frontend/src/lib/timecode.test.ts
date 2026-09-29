import { describe, expect, it } from "vitest";

import { formatTimecode, parseTimecode } from "./timecode";

describe("parseTimecode", () => {
  it("parses HH:MM:SS, MM:SS and seconds", () => {
    expect(parseTimecode("00:02:15")).toBe(135);
    expect(parseTimecode("2:15")).toBe(135);
    expect(parseTimecode("135")).toBe(135);
    expect(parseTimecode("1:02:03.5")).toBe(3723.5);
    expect(parseTimecode(" 0:45 ")).toBe(45);
  });

  it("rejects malformed input", () => {
    expect(parseTimecode("")).toBeNull();
    expect(parseTimecode("abc")).toBeNull();
    expect(parseTimecode("1:2:3:4")).toBeNull();
    expect(parseTimecode("00:75")).toBeNull();
    expect(parseTimecode("1:75:00")).toBeNull();
    expect(parseTimecode("-5")).toBeNull();
  });
});

describe("formatTimecode", () => {
  it("formats with and without hours", () => {
    expect(formatTimecode(135)).toBe("02:15");
    expect(formatTimecode(3723)).toBe("01:02:03");
    expect(formatTimecode(0)).toBe("00:00");
  });
});
