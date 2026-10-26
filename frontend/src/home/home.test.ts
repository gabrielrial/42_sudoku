import { describe, expect, it } from "vitest";

import { ApiError, type GameStarted, type Today } from "../api/client";
import { gameProblem, slotsOf, startOrResume } from "./home";

const STARTED: GameStarted = {
  game_id: "new-game",
  difficulty: "hard",
  date: "2026-10-26",
  givens: "0".repeat(81),
  state: "0".repeat(81),
  started_at: "2026-10-26T20:00:00+01:00",
};

const refusing = (error: unknown) => async (): Promise<GameStarted> => {
  throw error;
};

describe("slotsOf", () => {
  it("always shows the three difficulties, in order, even when one is missing", () => {
    const today: Today = {
      date: "2026-10-26",
      puzzles: [
        { difficulty: "hard", status: "completed", game_id: "h", official_seconds: 600, active_seconds: 540 },
        { difficulty: "easy", status: "not_started", game_id: null, official_seconds: null, active_seconds: null },
      ],
      continuing: [],
    };

    const slots = slotsOf(today);

    expect(slots.map((s) => s.difficulty)).toEqual(["easy", "medium", "hard"]);
    expect(slots.map((s) => s.puzzle?.status ?? null)).toEqual(["not_started", null, "completed"]);
  });
});

describe("startOrResume", () => {
  it("goes to the game it started", async () => {
    await expect(startOrResume(async () => STARTED, "hard")).resolves.toEqual({ gameId: "new-game" });
  });

  it("resumes the game that already exists: started in another tab, say", async () => {
    const exists = new ApiError("game_already_exists", 409, "…", { game_id: "old-game" });

    await expect(startOrResume(refusing(exists), "hard")).resolves.toEqual({ gameId: "old-game" });
  });

  it("does not trust a 409 that names no game", async () => {
    const odd = new ApiError("game_already_exists", 409, "…", { game_id: 7 });

    await expect(startOrResume(refusing(odd), "hard")).resolves.toHaveProperty("problem");
  });

  it("says when today's puzzle is not ready", async () => {
    const unavailable = new ApiError("puzzle_unavailable", 503, "…");

    await expect(startOrResume(refusing(unavailable), "easy")).resolves.toEqual({
      problem: "Today's puzzle is not ready yet. Try again later.",
    });
  });

  it("has a plain message for anything else, a lost network included", async () => {
    await expect(startOrResume(refusing(new TypeError("Failed to fetch")), "easy")).resolves.toEqual({
      problem: "The game could not be started. Try again.",
    });
  });
});

describe("gameProblem", () => {
  it.each([
    [new ApiError("game_not_found", 404, "…"), "There is no such game."],
    [new ApiError("game_closed", 410, "…"), /closed when its day ended/],
    [new TypeError("Failed to fetch"), "The game could not be loaded. Try again."],
  ])("explains %s", (error, message) => {
    expect(gameProblem(error)).toMatch(message);
  });
});
