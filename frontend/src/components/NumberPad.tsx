interface NumberPadProps {
  onDigit: (digit: number) => void;
  onErase: () => void;
  /** Notes mode: a digit is noted, not placed (D33). */
  noting: boolean;
  onToggleNotes: () => void;
  disabled: boolean;
}

const DIGITS = [1, 2, 3, 4, 5, 6, 7, 8, 9];

/** On-screen input, so the board can be played on a phone (DECISIONS.md Q6). */
export function NumberPad({ onDigit, onErase, noting, onToggleNotes, disabled }: NumberPadProps) {
  return (
    <div className={noting ? "pad pad--noting" : "pad"} aria-label="Number pad">
      {DIGITS.map((digit) => (
        <button
          key={digit}
          type="button"
          className="pad__key"
          disabled={disabled}
          onClick={() => onDigit(digit)}
        >
          {digit}
        </button>
      ))}
      <button
        type="button"
        className="pad__key pad__key--erase"
        disabled={disabled}
        onClick={onErase}
      >
        Erase
      </button>
      {/* Not disabled with the digits: the mode can be chosen before a cell. */}
      <button
        type="button"
        className="pad__key pad__key--notes"
        aria-pressed={noting}
        onClick={onToggleNotes}
      >
        {noting ? "Notes: on" : "Notes: off"}
      </button>
    </div>
  );
}
