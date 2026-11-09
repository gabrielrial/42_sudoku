import { type ReactNode, useCallback, useEffect, useState } from "react";

import { Board } from "../components/Board";
import { NumberPad } from "../components/NumberPad";
import { type Grid, moveFrom, type Notes } from "../game/grid";

const ARROWS: Record<string, [number, number]> = {
  ArrowUp: [-1, 0],
  ArrowDown: [1, 0],
  ArrowLeft: [0, -1],
  ArrowRight: [0, 1],
};

interface PlayPageProps {
  title: string;
  givens: Grid;
  values: Grid;
  notes: Notes;
  /** A finished or closed game: the grid is shown, nothing can be written. */
  readOnly: boolean;
  /** The decorative clock, if it runs. */
  clock: string | null;
  /** A line under the title: the result, or whether inputs are saved. */
  note: string | null;
  /** Under the pad: the check, and what it answered. */
  children?: ReactNode;
  /** `value` 0 clears the cell. Never called on a given or when read-only. */
  onWrite: (cell: number, value: number) => void;
  /** Adds or removes a note. Only on an empty cell that is not a given (D33). */
  onNote: (cell: number, digit: number) => void;
  onEraseNotes: (cell: number) => void;
}

/** The board and the number pad. What a write does is the caller's business. */
export function PlayPage({
  title,
  givens,
  values,
  notes,
  readOnly,
  clock,
  note,
  onWrite,
  onNote,
  onEraseNotes,
  children,
}: PlayPageProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const [noting, setNoting] = useState(false);

  const selectedIsEditable = !readOnly && selected !== null && givens[selected] === 0;

  const write = useCallback(
    (value: number) => {
      if (!selectedIsEditable || values[selected] === value) return;
      onWrite(selected, value);
    },
    [onWrite, selected, selectedIsEditable, values],
  );

  // A digit key: a note in notes mode, on an empty cell; otherwise the digit.
  const digit = useCallback(
    (value: number) => {
      if (!selectedIsEditable) return;
      if (noting) {
        if (values[selected] === 0) onNote(selected, value);
      } else {
        write(value);
      }
    },
    [noting, onNote, selected, selectedIsEditable, values, write],
  );

  // Erase takes away whatever the cell shows: its digit, or else its notes.
  const erase = useCallback(() => {
    if (!selectedIsEditable) return;
    if (values[selected] !== 0) write(0);
    else if (notes[selected] !== 0) onEraseNotes(selected);
  }, [notes, onEraseNotes, selected, selectedIsEditable, values, write]);

  // Hardware keyboard: digits write (or note), Backspace/Delete/0 erase,
  // N switches notes on and off, arrows move.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const arrow = ARROWS[event.key];
      if (arrow) {
        event.preventDefault();
        setSelected((cell) => (cell === null ? 0 : moveFrom(cell, arrow[0], arrow[1])));
      } else if (/^[1-9]$/.test(event.key)) {
        digit(Number(event.key));
      } else if (event.key === "Backspace" || event.key === "Delete" || event.key === "0") {
        erase();
      } else if (event.key === "n" || event.key === "N") {
        setNoting((on) => !on);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [digit, erase]);

  return (
    <main className="play">
      <h1 className="play__title">{title}</h1>
      {clock !== null && (
        <p className="play__clock" aria-label="Time since you started">
          {clock}
        </p>
      )}
      {note !== null && (
        <p className="play__note" aria-live="polite">
          {note}
        </p>
      )}
      <Board
        givens={givens}
        values={values}
        notes={notes}
        selected={selected}
        onSelect={setSelected}
      />
      {!readOnly && (
        <NumberPad
          onDigit={digit}
          onErase={erase}
          noting={noting}
          onToggleNotes={() => setNoting((on) => !on)}
          disabled={!selectedIsEditable}
        />
      )}
      {children}
    </main>
  );
}
