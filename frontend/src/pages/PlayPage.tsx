import { useCallback, useEffect, useMemo, useState } from "react";

import { Board } from "../components/Board";
import { NumberPad } from "../components/NumberPad";
import { type Grid, moveFrom, parseGrid, setCell } from "../game/grid";

const ARROWS: Record<string, [number, number]> = {
  ArrowUp: [-1, 0],
  ArrowDown: [1, 0],
  ArrowLeft: [0, -1],
  ArrowRight: [0, 1],
};

interface PlayPageProps {
  title: string;
  /** 81 characters each, as the API sends them (DATA_MODEL.md). */
  givens: string;
  state: string;
  /** A completed game: the grid is shown, nothing can be written. */
  readOnly: boolean;
  note: string | null;
}

/**
 * The board and the number pad. Inputs change the board in memory only; the
 * API calls that make them count are PLAN.md 6c.
 */
export function PlayPage({ title, givens: givensText, state, readOnly, note }: PlayPageProps) {
  const givens = useMemo(() => parseGrid(givensText), [givensText]);
  const [values, setValues] = useState<Grid>(() => parseGrid(state));
  const [selected, setSelected] = useState<number | null>(null);

  const selectedIsEditable = !readOnly && selected !== null && givens[selected] === 0;

  const write = useCallback(
    (value: number) => {
      if (readOnly || selected === null) return;
      setValues((current) => setCell(current, givens, selected, value));
    },
    [givens, readOnly, selected],
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
