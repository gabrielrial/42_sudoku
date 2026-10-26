// The home page's decisions, without React: which slots it shows, how a game
// is started, and what a failure says.

import { ApiError, type Difficulty, type GameStarted, type Today, type TodayPuzzle } from "../api/client";

export const DIFFICULTIES: readonly Difficulty[] = ["easy", "medium", "hard"];

export interface Slot {
  difficulty: Difficulty;
  /** `null` when today has no puzzle of this difficulty (API.md leaves it out). */
  puzzle: TodayPuzzle | null;
}

/** Always the three difficulties, in order (Q7): a missing one is shown as
 * unavailable rather than leaving a hole in the layout. */
export function slotsOf(today: Today): Slot[] {
  return DIFFICULTIES.map((difficulty) => ({
    difficulty,
    puzzle: today.puzzles.find((p) => p.difficulty === difficulty) ?? null,
  }));
}

export type StartOutcome = { gameId: string } | { problem: string };

/**
 * Start today's game of `difficulty`. A game that already exists (started in
 * another tab, say) is not a failure: the `409` names it, and it is resumed.
 */
export async function startOrResume(
  start: (difficulty: Difficulty) => Promise<GameStarted>,
  difficulty: Difficulty,
): Promise<StartOutcome> {
  try {
    return { gameId: (await start(difficulty)).game_id };
  } catch (error) {
    if (error instanceof ApiError) {
      const existing = error.details.game_id;
      if (error.code === "game_already_exists" && typeof existing === "string") {
        return { gameId: existing };
      }
      if (error.code === "puzzle_unavailable") {
        return { problem: "Today's puzzle is not ready yet. Try again later." };
      }
    }
    return { problem: "The game could not be started. Try again." };
  }
}

/** What the game page says when a game cannot be shown. */
export function gameProblem(error: unknown): string {
  if (error instanceof ApiError && error.code === "game_not_found") return "There is no such game.";
  if (error instanceof ApiError && error.code === "game_closed") {
    return "This game was closed when its day ended. Today's puzzles are on the home page.";
  }
  return "The game could not be loaded. Try again.";
}
