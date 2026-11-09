import { describe, expect, it } from "vitest";

import { digitEffect, eraseEffect, keyAction } from "./play";

describe("a key", () => {
  it.each([
    ["1", { kind: "digit", digit: 1 }],
    ["9", { kind: "digit", digit: 9 }],
    ["0", { kind: "erase" }],
    ["Backspace", { kind: "erase" }],
    ["Delete", { kind: "erase" }],
    ["n", { kind: "toggle-notes" }],
    ["N", { kind: "toggle-notes" }],
    ["ArrowUp", { kind: "move", rows: -1, cols: 0 }],
    ["ArrowRight", { kind: "move", rows: 0, cols: 1 }],
  ])("%s", (key, action) => {
    expect(keyAction(key)).toEqual(action);
  });

  it.each(["a", "Enter", " ", "10"])("%s is not the board's", (key) => {
    expect(keyAction(key)).toBeNull();
  });
});

describe("a digit", () => {
  it("is written outside notes mode", () => {
    expect(digitEffect(false, 0, 4)).toEqual({ kind: "write", value: 4 });
    expect(digitEffect(false, 7, 4)).toEqual({ kind: "write", value: 4 });
  });

  it("does nothing when the cell already holds it", () => {
    expect(digitEffect(false, 4, 4)).toBeNull();
  });

  it("is noted in notes mode, on an empty cell only", () => {
    expect(digitEffect(true, 0, 4)).toEqual({ kind: "note", digit: 4 });
    expect(digitEffect(true, 7, 4)).toBeNull(); // the server would refuse it (409)
  });
});

describe("erase", () => {
  it("takes the digit first, then the notes, then nothing", () => {
    expect(eraseEffect(5, 0b11)).toBe("digit");
    expect(eraseEffect(0, 0b11)).toBe("notes");
    expect(eraseEffect(0, 0)).toBeNull();
  });
});
