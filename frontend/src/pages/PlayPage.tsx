import { type ReactNode, useCallback, useEffect, useState } from "react";

import { Board } from "../components/Board";
import { NumberPad } from "../components/NumberPad";
import { type Grid, moveFrom, type Notes } from "../game/grid";
import { digitEffect, eraseEffect, keyAction } from "../game/play";

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

  const digit = useCallback(
    (value: number) => {
      if (!selectedIsEditable) return;
      const effect = digitEffect(noting, values[selected]!, value);
      if (effect?.kind === "note") onNote(selected, effect.digit);
      else if (effect?.kind === "write") write(effect.value);
    },
    [noting, onNote, selected, selectedIsEditable, values, write],
  );

  const erase = useCallback(() => {
    if (!selectedIsEditable) return;
    const effect = eraseEffect(values[selected]!, notes[selected]!);
    if (effect === "digit") write(0);
    else if (effect === "notes") onEraseNotes(selected);
  }, [notes, onEraseNotes, selected, selectedIsEditable, values, write]);

  // Hardware keyboard: what each key does is `keyAction`'s (game/play.ts).
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const action = keyAction(event.key);
      if (action?.kind === "move") {
        event.preventDefault();
        setSelected((cell) =>
          cell === null ? 0 : moveFrom(cell, action.rows, action.cols),
        );
      } else if (action?.kind === "digit") {
        digit(action.digit);
      } else if (action?.kind === "erase") {
        erase();
      } else if (action?.kind === "toggle-notes") {
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
