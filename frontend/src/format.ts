/** Whole seconds as `m:ss`, or `h:mm:ss` from an hour on. */
export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

const LABELS = { easy: "Easy", medium: "Medium", hard: "Hard" } as const;

export const difficultyLabel = (difficulty: keyof typeof LABELS): string => LABELS[difficulty];
