import { describe, expect, it } from "vitest";
import { area, deedType, fieldLabel, price, text } from "./format";

describe("values", () => {
  it("shows missing values as empty and objects as JSON", () => {
    expect(text(null)).toBe("");
    expect(text(undefined)).toBe("");
    expect(text(0)).toBe("0");
    expect(text({ a: 1 })).toBe('{"a":1}');
  });

  it("formats euros and square metres the Greek way", () => {
    expect(price(185000)).toMatch(/^185\.000,00\s€$/u);
    expect(area(85.4)).toBe("85,4 m²");
    expect(price("not a number")).toBe("not a number"); // shown as written, flagged by validation
  });

  it("names deed types", () => {
    expect(deedType("parental_provision")).toBe("Parental provision");
    expect(deedType("lease")).toBe("lease");
  });
});

describe("fieldLabel", () => {
  it("names a party's field with a 1-based number", () => {
    expect(fieldLabel("sellers[0].tax_id")).toBe("Seller 1 · tax ID (ΑΦΜ)");
    expect(fieldLabel("legal_representatives[1].full_name")).toBe("Representative 2 · name");
  });

  it("names section fields and whole lists", () => {
    expect(fieldLabel("property.kaek")).toBe("Property · ΚΑΕΚ");
    expect(fieldLabel("transaction.deed_type")).toBe("Transaction · deed type");
    expect(fieldLabel("buyers")).toBe("Buyers");
  });
});
