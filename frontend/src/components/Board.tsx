import { colOf, digitsOf, type Grid, type Notes, rowOf } from "../game/grid";

const DIGITS = [1, 2, 3, 4, 5, 6, 7, 8, 9];

interface BoardProps {
  givens: Grid;
  values: Grid;
  notes: Notes;
  selected: number | null;
  onSelect: (cell: number) => void;
}

/**
 * The 9×9 grid. Purely presentational: it shows what it is given and reports
 * which cell was tapped. Every cell is a button, so it works by touch, by
 * mouse and with the keyboard's Tab key alike.
 */
export function Board({ givens, values, notes, selected, onSelect }: BoardProps) {
  return (
    <div className="board" role="grid" aria-label="Sudoku board">
      {values.map((value, cell) => {
        const given = givens[cell] !== 0;
        const noted = value === 0 ? digitsOf(notes[cell] ?? 0) : [];
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
              value !== 0
                ? given
                  ? `${value}, given`
                  : value
                : noted.length > 0
                  ? `empty, notes ${noted.join(" ")}`
                  : "empty"
            }`}
            onClick={() => onSelect(cell)}
          >
            {value !== 0 ? (
              value
            ) : noted.length > 0 ? (
              // Each digit in its own place of a 3×3, so a 7 is always bottom left.
              <span className="cell__notes" aria-hidden="true">
                {DIGITS.map((d) => (
                  <span key={d}>{noted.includes(d) ? d : ""}</span>
                ))}
              </span>
            ) : (
              ""
            )}
          </button>
        );
      })}
    </div>
  );
}
