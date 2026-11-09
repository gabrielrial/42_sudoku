import { describe, expect, it } from "vitest";

import {
  clearNotes,
  digitsOf,
  NO_NOTES,
  notesAfterWrite,
  notesFromApi,
  PEERS,
  placeDigit,
  toggleNote,
} from "./grid";

describe("notes", () => {
  it("come from the API's lists and go back as digits", () => {
    const lists = Array.from({ length: 81 }, () => [] as number[]);
    lists[4] = [9, 1, 5];

    const notes = notesFromApi(lists);

    expect(digitsOf(notes[4]!)).toEqual([1, 5, 9]);
    expect(notes.filter((mask) => mask !== 0)).toHaveLength(1);
  });

  it("refuse a list that is not 81 cells long", () => {
    expect(() => notesFromApi([[1]])).toThrow();
  });

  it("toggle a digit on and off", () => {
    const on = toggleNote(NO_NOTES, 10, 3);
    expect(digitsOf(on[10]!)).toEqual([3]);
    expect(toggleNote(on, 10, 3)[10]).toBe(0);
  });

  it("clear one cell, leaving the others", () => {
    const notes = toggleNote(toggleNote(NO_NOTES, 1, 2), 2, 2);

    const cleared = clearNotes(notes, 1);

    expect(cleared[1]).toBe(0);
    expect(cleared[2]).toBe(notes[2]);
  });
});

describe("peers", () => {
  it("are the 20 cells sharing a row, a column or a box", () => {
    expect(PEERS[0]).toHaveLength(20);
    expect(PEERS[0]).toEqual(expect.arrayContaining([1, 8, 9, 72, 10, 20]));
    expect(PEERS[0]).not.toContain(0);
    expect(PEERS[0]).not.toContain(30); // row 3, column 3: nothing shared
  });

  it("are the same for every cell of the board", () => {
    PEERS.forEach((peers) => expect(peers).toHaveLength(20));
  });
});

describe("writing a cell", () => {
  it("prunes with a digit, as the server does", () => {
    const notes = toggleNote(NO_NOTES, 1, 4);

    expect(notesAfterWrite(notes, 0, 4)[1]).toBe(0);
  });

  it("brings nothing back, and takes nothing, when the cell is emptied", () => {
    const notes = toggleNote(NO_NOTES, 1, 4);

    expect(notesAfterWrite(notes, 0, 0)).toBe(notes);
  });
});

describe("placing a digit", () => {
  it("clears its cell and takes the digit out of its row, column and box", () => {
    let notes = NO_NOTES;
    for (const [cell, digit] of [
      [0, 4], [0, 5], // the cell itself
      [8, 4], [8, 6], // same row
      [72, 4], // same column
      [20, 4], // same box
      [30, 4], // nothing shared
    ] as const) {
      notes = toggleNote(notes, cell, digit);
    }

    const placed = placeDigit(notes, 0, 4);

    expect(placed[0]).toBe(0);
    expect(digitsOf(placed[8]!)).toEqual([6]);
    expect(placed[72]).toBe(0);
    expect(placed[20]).toBe(0);
    expect(digitsOf(placed[30]!)).toEqual([4]);
  });
});
