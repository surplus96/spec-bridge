import { describe, expect, it } from "vitest";
import { contextParts, formatValue } from "./format";

describe("format", () => {
  it("shows dimensions as L × W × H whatever the stored key order", () => {
    expect(formatValue({ height: 2600, length: 4400, width: 1900 })).toBe(
      "L 4400 × W 1900 × H 2600",
    );
    expect(formatValue({ length: 1160 })).toBe("L 1160");
  });

  it("leaves out axes that state nothing (seed rows store every axis)", () => {
    const seed = {
      basis: { capacity: "unknown", rating: "continuous_engine_shaft", pressure: "not_applicable" },
      condition: { rating_point: "R1", frequency: null, medium: null },
      scope: "engine_shaft",
    };
    expect(contextParts(seed).map((p) => `${p.name}: ${p.value}`)).toEqual([
      "rating: continuous engine shaft",
      "rating point: R1",
      "범위: engine shaft",
    ]);
    expect(
      contextParts({ basis: { weight: "unknown" }, condition: {}, scope: "main_equipment" }),
    ).toEqual([]);
  });

  it("reads booleans and tokens as words", () => {
    expect(formatValue(true)).toBe("예");
    expect(formatValue("heavy_fuel_oil")).toBe("heavy fuel oil");
  });
});
