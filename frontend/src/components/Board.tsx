import { colOf, type Grid, rowOf } from "../game/grid";

interface BoardProps {
  givens: Grid;
  values: Grid;
  selected: number | null;
  onSelect: (cell: number) => void;
}

/**
 * The 9×9 grid. Purely presentational: it shows what it is given and reports
 * which cell was tapped. Every cell is a button, so it works by touch, by
 * mouse and with the keyboard's Tab key alike.
 */
export function Board({ givens, values, selected, onSelect }: BoardProps) {
  return (
    <div className="board" role="grid" aria-label="Sudoku board">
      {values.map((value, cell) => {
        const given = givens[cell] !== 0;
        const row = rowOf(cell);
        const col = colOf(cell);
        const classes = ["cell"];
        if (given) classes.push("cell--given");
        if (cell === selected) classes.push("cell--selected");
        if (col % 3 === 2 && col !== 8) classes.push("cell--box-right");
        if (row % 3 === 2 && row !== 8) classes.push("cell--box-bottom");

        return (
          <button
            key={cell}
            type="button"
            role="gridcell"
            className={classes.join(" ")}
            aria-selected={cell === selected}
            aria-label={`Row ${row + 1}, column ${col + 1}: ${
              value === 0 ? "empty" : given ? `${value}, given` : value
            }`}
            onClick={() => onSelect(cell)}
          >
            {value === 0 ? "" : value}
          </button>
        );
      })}
    </div>
  );
}
