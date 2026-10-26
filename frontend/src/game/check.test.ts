import { describe, expect, it, vi } from "vitest";

import { ApiError, type CompletionResult } from "../api/client";
import { checkGrid, elapsedSeconds } from "./check";

const saved = async () => true;
const answer = (result: CompletionResult) => async () => result;
const refuse = (error: unknown) => async (): Promise<CompletionResult> => {
  throw error;
};

describe("checkGrid", () => {
  it("waits for every input to be saved before asking: the server checks its own grid", async () => {
    const order: string[] = [];
    let release!: (saved: boolean) => void;
    const pending = new Promise<boolean>((resolve) => (release = resolve));
    const complete = vi.fn(async () => {
      order.push("complete");
      return { correct: false, submission_count: 1 };
    });

    const checking = checkGrid(() => {
      order.push("waiting for inputs");
      return pending;
    }, complete);
    await Promise.resolve();
    expect(complete).not.toHaveBeenCalled();

    release(true);
    await checking;
    expect(order).toEqual(["waiting for inputs", "complete"]);
  });

  it("does not ask when the inputs could not be saved", async () => {
    const complete = vi.fn(answer({ correct: true, submission_count: 1 }));

    const outcome = await checkGrid(async () => false, complete);

    expect(outcome.kind).toBe("problem");
    expect(complete).not.toHaveBeenCalled();
  });

  it("is solved, with the server's times", async () => {
    const outcome = await checkGrid(
      saved,
      answer({ correct: true, submission_count: 2, official_seconds: 1187, active_seconds: 964 }),
    );

    expect(outcome).toEqual({ kind: "solved", officialSeconds: 1187, activeSeconds: 964 });
  });

  it("is wrong, and says only that, with the count", async () => {
    await expect(checkGrid(saved, answer({ correct: false, submission_count: 3 }))).resolves.toEqual({
      kind: "wrong",
      submissions: 3,
    });
  });

  it("is closed when the day ended, however right the grid", async () => {
    const closed = new ApiError("game_closed", 410, "…");

    await expect(checkGrid(saved, refuse(closed))).resolves.toEqual({ kind: "closed" });
  });

  it.each([
    [new ApiError("too_many_requests", 429, "…", {}, 12), "Too many checks. Try again in 12 seconds."],
    [new ApiError("grid_incomplete", 409, "…"), /Reload the game/],
    [new TypeError("Failed to fetch"), /cannot be reached/],
    [new ApiError("unknown_error", 500, "…"), "The grid could not be checked. Try again."],
  ])("explains %s", async (error, message) => {
    const outcome = await checkGrid(saved, refuse(error));

    expect(outcome.kind).toBe("problem");
    expect(outcome.kind === "problem" && outcome.message).toMatch(message);
  });
});

describe("elapsedSeconds", () => {
  const started = "2026-10-26T20:00:00+01:00";
  const at = (iso: string) => Date.parse(iso);

  it("counts whole seconds since the start, whatever offset the start was written in", () => {
    expect(elapsedSeconds(started, at("2026-10-26T19:19:47Z"))).toBe(1187);
  });

  it("never goes below zero when this device's clock is behind", () => {
    expect(elapsedSeconds(started, at("2026-10-26T18:59:00Z"))).toBe(0);
  });
});
