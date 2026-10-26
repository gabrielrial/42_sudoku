// Checking a full grid (GAME_RULES.md §4). The server checks the grid it
// holds, not the one on screen, so every input must have reached it first.
// No React in here.

import { ApiError, type CompletionResult } from "../api/client";

export type CheckOutcome =
  | { kind: "solved"; officialSeconds: number; activeSeconds: number }
  /** Right or wrong is all the answer says: never which cells (SECURITY.md). */
  | { kind: "wrong"; submissions: number }
  | { kind: "closed" }
  | { kind: "problem"; message: string };

export async function checkGrid(
  saved: () => Promise<boolean>,
  complete: () => Promise<CompletionResult>,
): Promise<CheckOutcome> {
  if (!(await saved())) {
    // The input queue stopped; it says why, and the page shows that.
    return { kind: "problem", message: "The grid could not be checked." };
  }
  try {
    const result = await complete();
    if (!result.correct) return { kind: "wrong", submissions: result.submission_count };
    return {
      kind: "solved",
      officialSeconds: result.official_seconds ?? 0,
      activeSeconds: result.active_seconds ?? 0,
    };
  } catch (error) {
    if (!(error instanceof ApiError)) {
      return { kind: "problem", message: "The server cannot be reached. Try again in a moment." };
    }
    if (error.code === "game_closed") return { kind: "closed" };
    if (error.status === 429) {
      const wait = error.retryAfterSeconds ?? 60;
      return { kind: "problem", message: `Too many checks. Try again in ${wait} seconds.` };
    }
    if (error.code === "grid_incomplete") {
      // Every input was saved, so the server and the screen disagree: the
      // screen is what is out of date (another tab, say).
      return { kind: "problem", message: "Some cells are empty on the server. Reload the game." };
    }
    return { kind: "problem", message: "The grid could not be checked. Try again." };
  }
}

/** The decorative clock: time since the game started, by this device's
 * clock. Never sent anywhere and never trusted (GAME_RULES.md §4). */
export function elapsedSeconds(startedAt: string, now: number): number {
  return Math.max(0, Math.floor((now - Date.parse(startedAt)) / 1000));
}
