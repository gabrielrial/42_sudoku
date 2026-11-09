// What a key or a pad button does on the board. No React in here, so it can
// be tested without a browser.

export type KeyAction =
  | { kind: "move"; rows: number; cols: number }
  | { kind: "digit"; digit: number }
  | { kind: "erase" }
  | { kind: "toggle-notes" };

const ARROWS: Record<string, [number, number]> = {
  ArrowUp: [-1, 0],
  ArrowDown: [1, 0],
  ArrowLeft: [0, -1],
  ArrowRight: [0, 1],
};

/** Digits write (or note), Backspace/Delete/0 erase, N switches notes on and
 * off, arrows move. Anything else is not the board's. */
export function keyAction(key: string): KeyAction | null {
  const arrow = ARROWS[key];
  if (arrow) return { kind: "move", rows: arrow[0], cols: arrow[1] };
  if (/^[1-9]$/.test(key)) return { kind: "digit", digit: Number(key) };
  if (key === "Backspace" || key === "Delete" || key === "0") return { kind: "erase" };
  if (key === "n" || key === "N") return { kind: "toggle-notes" };
  return null;
}

export type DigitEffect = { kind: "write"; value: number } | { kind: "note"; digit: number } | null;

/** A digit on an editable cell: a note in notes mode, and only on an empty
 * cell (a placed digit has no notes, D33); otherwise the digit itself. */
export function digitEffect(noting: boolean, cellValue: number, digit: number): DigitEffect {
  if (noting) return cellValue === 0 ? { kind: "note", digit } : null;
  return cellValue === digit ? null : { kind: "write", value: digit };
}

/** Erase takes away what the cell shows: its digit, or else its notes. */
export function eraseEffect(cellValue: number, cellNotes: number): "digit" | "notes" | null {
  if (cellValue !== 0) return "digit";
  return cellNotes !== 0 ? "notes" : null;
}
