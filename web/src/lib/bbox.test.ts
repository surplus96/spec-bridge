import { describe, expect, it } from "vitest";
import { toScreenBox } from "./bbox";

describe("toScreenBox", () => {
  it("flips y: a box near the top of the page lands near the top of the screen", () => {
    // A4-like page 842 pt high; box from y=800 to y=820 (bottom-left origin).
    expect(toScreenBox([50, 800, 150, 820], 842, 1)).toEqual({
      left: 50,
      top: 22,
      width: 100,
      height: 20,
    });
  });

  it("scales every side with the rendered size", () => {
    expect(toScreenBox([50, 800, 150, 820], 842, 2)).toEqual({
      left: 100,
      top: 44,
      width: 200,
      height: 40,
    });
  });

  it("puts a box at the bottom of the page at the bottom of the screen", () => {
    const box = toScreenBox([0, 0, 10, 10], 100, 1);
    expect(box.top + box.height).toBe(100);
  });
});
