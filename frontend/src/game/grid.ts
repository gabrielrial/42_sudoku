// Grid helpers. No React in here, so they are easy to reason about and to test.
//
// A grid is 81 numbers, row by row, 0 for an empty cell — the same layout as
// the 81-character strings the API sends (DATA_MODEL.md). Cell `i` is in row
// `Math.floor(i / 9)` and column `i % 9`.

export type Grid = readonly number[];

export const CELL_COUNT = 81;

export function parseGrid(text: string): number[] {
  if (!/^[0-9]{81}$/.test(text)) {
    throw new Error("A grid is exactly 81 characters, each 0-9.");
  }
  return Array.from(text, Number);
}

export const rowOf = (cell: number): number => Math.floor(cell / 9);
export const colOf = (cell: number): number => cell % 9;

/**
 * The grid with `value` written into `cell` (0 clears it).
 *
 * Givens cannot be changed: the same grid comes back untouched. The backend
 * enforces this as well (`409 cell_is_given`); the check here only keeps the
 * interface from pretending otherwise.
 */
export function setCell(values: Grid, givens: Grid, cell: number, value: number): Grid {
  if (givens[cell] !== 0 || values[cell] === value) return values;
  const next = values.slice();
  next[cell] = value;
  return next;
}

/** Each cell's notes as a bitmask, bit `d - 1` for digit `d` (D33): the same
 * layout the database keeps. The API sends them as lists of digits. */
export type Notes = readonly number[];

export const NO_NOTES: Notes = Array.from({ length: CELL_COUNT }, () => 0);

export function notesFromApi(lists: readonly (readonly number[])[]): number[] {
  if (lists.length !== CELL_COUNT) throw new Error("Notes come for exactly 81 cells.");
  return lists.map((digits) => digits.reduce((mask, digit) => mask | (1 << (digit - 1)), 0));
}

/** The digits noted in a cell, ascending. */
export function digitsOf(mask: number): number[] {
  return [1, 2, 3, 4, 5, 6, 7, 8, 9].filter((digit) => mask & (1 << (digit - 1)));
}

/** The notes with `digit` added to `cell`, or taken out if it was there. */
export function toggleNote(notes: Notes, cell: number, digit: number): Notes {
  const next = notes.slice();
  next[cell] = notes[cell]! ^ (1 << (digit - 1));
  return next;
}

export function clearNotes(notes: Notes, cell: number): Notes {
  if (notes[cell] === 0) return notes;
  const next = notes.slice();
  next[cell] = 0;
  return next;
}

const boxOf = (cell: number): number => Math.floor(rowOf(cell) / 3) * 3 + Math.floor(colOf(cell) / 3);

/** For each cell, the 20 others in its row, column or box. */
export const PEERS: readonly (readonly number[])[] = Array.from({ length: CELL_COUNT }, (_, cell) =>
  Array.from({ length: CELL_COUNT }, (_, other) => other).filter(
    (other) =>
      other !== cell &&
      (rowOf(other) === rowOf(cell) || colOf(other) === colOf(cell) || boxOf(other) === boxOf(cell)),
  ),
);

/**
 * The notes once `value` is placed in `cell`: none left there, and `value`
 * gone from its row, column and box (GAME_RULES.md §3). The server does the
 * same on its side; this keeps the screen from waiting for it.
 */
export function placeDigit(notes: Notes, cell: number, value: number): Notes {
  const bit = 1 << (value - 1);
  const next = notes.slice();
  next[cell] = 0;
  for (const peer of PEERS[cell]!) next[peer] = next[peer]! & ~bit;
  return next;
}

/** The cell reached by moving from `cell` by the given rows and columns,
 * stopping at the edge of the board. */
export function moveFrom(cell: number, rows: number, cols: number): number {
  const row = Math.min(8, Math.max(0, rowOf(cell) + rows));
  const col = Math.min(8, Math.max(0, colOf(cell) + cols));
  return row * 9 + col;
}
