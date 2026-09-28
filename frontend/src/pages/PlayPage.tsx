import { useCallback, useEffect, useMemo, useState } from "react";

import { Board } from "../components/Board";
import { NumberPad } from "../components/NumberPad";
import { DEMO_GIVENS } from "../game/demoPuzzle";
import { type Grid, moveFrom, parseGrid, setCell } from "../game/grid";

const ARROWS: Record<string, [number, number]> = {
  ArrowUp: [-1, 0],
  ArrowDown: [1, 0],
  ArrowLeft: [0, -1],
  ArrowRight: [0, 1],
};

/**
 * One puzzle you can fill in, and nothing else yet: no timer, no checking, no
 * saving. The grid lives in memory only, so a reload starts it over.
 */
export function PlayPage() {
  const givens = useMemo(() => parseGrid(DEMO_GIVENS), []);
  const [values, setValues] = useState<Grid>(givens);
  const [selected, setSelected] = useState<number | null>(null);

  const selectedIsEditable = selected !== null && givens[selected] === 0;

  const write = useCallback(
    (value: number) => {
      if (selected === null) return;
      setValues((current) => setCell(current, givens, selected, value));
    },
    [givens, selected],
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
      <h1 className="play__title">Sudoku 42</h1>
      <Board givens={givens} values={values} selected={selected} onSelect={setSelected} />
      <NumberPad onDigit={write} onErase={() => write(0)} disabled={!selectedIsEditable} />
    </main>
  );
}
