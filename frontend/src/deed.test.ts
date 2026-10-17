import { describe, expect, it } from "vitest";
import { getPath, isNumberField, parseNumber, setPath, tryGetPath } from "./deed";
import type { Deed } from "./types";

const deed: Deed = {
  notary: { name: "Κωνσταντίνος Δοκιμαστής", location: "Πειραιάς", registry_number: "11.954" },
  sellers: [
    { full_name: "Αικατερίνη Πλασματική", tax_id: "777679361" },
    { full_name: "Μαρία Εικονική", tax_id: "141169610" },
  ],
  buyers: [],
  property: { kaek: "995296326976/0/6", area_sqm: 850.53 },
};

describe("getPath", () => {
  it("reads a section field and a party's field", () => {
    expect(getPath(deed, "property.kaek")).toBe("995296326976/0/6");
    expect(getPath(deed, "sellers[1].tax_id")).toBe("141169610");
  });

  it("returns undefined for a party or section that is not there", () => {
    expect(getPath(deed, "sellers[5].tax_id")).toBeUndefined();
    expect(getPath(deed, "buyers[0].full_name")).toBeUndefined();
    expect(getPath(deed, "transaction.price")).toBeUndefined();
  });

  it("rejects a path that is not a single field", () => {
    expect(() => getPath(deed, "sellers")).toThrow("Bad field path");
    expect(tryGetPath(deed, "sellers")).toBeUndefined();
  });
});

describe("setPath", () => {
  it("returns a changed copy and leaves the original alone", () => {
    const next = setPath(deed, "sellers[0].tax_id", "999999999");
    expect(getPath(next, "sellers[0].tax_id")).toBe("999999999");
    expect(getPath(next, "sellers[1].tax_id")).toBe("141169610");
    expect(getPath(deed, "sellers[0].tax_id")).toBe("777679361");
    expect(next.sellers).not.toBe(deed.sellers);
  });

  it("creates a missing section", () => {
    const next = setPath(deed, "transaction.price", 111500);
    expect(next.transaction).toEqual({ price: 111500 });
    expect(next.property).toBe(deed.property); // untouched sections are shared, not copied
  });
});

describe("parseNumber", () => {
  it("reads Greek and plain formats", () => {
    expect(parseNumber("185.000,50")).toBe(185000.5);
    expect(parseNumber("185000.5")).toBe(185000.5);
    expect(parseNumber(" 85,4 ")).toBe(85.4);
    expect(parseNumber("185.000,00 €")).toBe(185000);
  });

  it("keeps empty as null and nonsense as text, so validation can flag it", () => {
    expect(parseNumber("  ")).toBeNull();
    expect(parseNumber("about a hundred")).toBe("about a hundred");
  });

  it("knows which fields are numbers", () => {
    expect(isNumberField("property.area_sqm")).toBe(true);
    expect(isNumberField("transaction.price")).toBe(true);
    expect(isNumberField("property.kaek")).toBe(false);
  });
});
