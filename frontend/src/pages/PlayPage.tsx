import { useCallback, useEffect, useState } from "react";

import { Board } from "../components/Board";
import { NumberPad } from "../components/NumberPad";
import { type Grid, moveFrom } from "../game/grid";

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
  /** A finished or closed game: the grid is shown, nothing can be written. */
  readOnly: boolean;
  /** A line under the title: the result, or whether inputs are saved. */
  note: string | null;
  /** `value` 0 clears the cell. Never called on a given or when read-only. */
  onWrite: (cell: number, value: number) => void;
}

/** The board and the number pad. What a write does is the caller's business. */
export function PlayPage({ title, givens, values, readOnly, note, onWrite }: PlayPageProps) {
  const [selected, setSelected] = useState<number | null>(null);

  const selectedIsEditable = !readOnly && selected !== null && givens[selected] === 0;

  const write = useCallback(
    (value: number) => {
      if (!selectedIsEditable || values[selected] === value) return;
      onWrite(selected, value);
    },
    [onWrite, selected, selectedIsEditable, values],
  );

  // Hardware keyboard: digits write, Backspace/Delete/0 clear, arrows move.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const arrow = ARROWS[event.key];
      if (arrow) {
        event.preventDefault();
        setSelected((cell) => (cell === null ? 0 : moveFrom(cell, arrow[0], arrow[1])));
      } else if (/^[1-9]$/.test(event.key)) {
        write(Number(event.key));
      } else if (event.key === "Backspace" || event.key === "Delete" || event.key === "0") {
        write(0);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [write]);

  return (
    <main className="play">
      <h1 className="play__title">{title}</h1>
      {note !== null && <p className="play__note">{note}</p>}
      <Board givens={givens} values={values} selected={selected} onSelect={setSelected} />
      {!readOnly && (
        <NumberPad onDigit={write} onErase={() => write(0)} disabled={!selectedIsEditable} />
      )}
    </main>
  );
}
