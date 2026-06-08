import { describe, expect, it } from "vitest";
import {
  currentFinancialYear,
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPct,
  gainClass,
  recentFinancialYears,
} from "./format";

describe("formatCurrency", () => {
  it("formats AUD with symbol", () => {
    expect(formatCurrency(1234.5)).toBe("$1,234.50");
  });
  it("renders a dash for null/NaN", () => {
    expect(formatCurrency(null)).toBe("—");
    expect(formatCurrency(NaN)).toBe("—");
  });
});

describe("formatPct", () => {
  it("formats with two decimals", () => {
    expect(formatPct(12.345)).toBe("12.35%");
  });
  it("adds a + sign for positive values when requested", () => {
    expect(formatPct(5, true)).toBe("+5.00%");
    expect(formatPct(-5, true)).toBe("-5.00%");
    expect(formatPct(0, true)).toBe("0.00%");
  });
  it("renders a dash for null", () => {
    expect(formatPct(null)).toBe("—");
  });
});

describe("formatNumber", () => {
  it("groups thousands", () => {
    expect(formatNumber(1000000)).toBe("1,000,000");
  });
});

describe("gainClass", () => {
  it("classifies sign", () => {
    expect(gainClass(10)).toBe("positive");
    expect(gainClass(-10)).toBe("negative");
    expect(gainClass(0)).toBe("neutral");
    expect(gainClass(null)).toBe("neutral");
  });
});

describe("formatDateTime", () => {
  it("returns a dash for empty input", () => {
    expect(formatDateTime(null)).toBe("—");
  });
  it("parses a naive UTC timestamp without throwing", () => {
    expect(formatDateTime("2024-01-01T00:00:00")).not.toBe("—");
  });
});

describe("financial year helpers", () => {
  it("derives the AU FY from a date (July rolls over)", () => {
    expect(currentFinancialYear(new Date("2024-06-30"))).toBe("2023-24");
    expect(currentFinancialYear(new Date("2024-07-01"))).toBe("2024-25");
    expect(currentFinancialYear(new Date("2025-01-15"))).toBe("2024-25");
  });
  it("lists recent FYs newest first", () => {
    expect(recentFinancialYears(3, new Date("2025-01-15"))).toEqual([
      "2024-25",
      "2023-24",
      "2022-23",
    ]);
  });
});
