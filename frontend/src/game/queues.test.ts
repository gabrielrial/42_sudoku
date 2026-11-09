import { describe, expect, it } from "vitest";

import { ApiError, type GameView } from "../api/client";
import { createInputQueue } from "./inputQueue";
import { createQueueRegistry } from "./queues";

const GAME: GameView = {
  game_id: "g",
  difficulty: "easy",
  date: "2026-10-26",
  givens: "0".repeat(81),
  state: "0".repeat(81),
  notes: Array.from({ length: 81 }, () => []),
  status: "in_progress",
  started_at: "2026-10-26T20:00:00+01:00",
  completed_at: null,
  official_seconds: null,
  active_seconds: 0,
  submission_count: 0,
};

/** A put whose answers are held until released, one gate per request. */
function heldPut(failWith?: unknown) {
  const gates: Array<() => void> = [];
  const sent: number[] = [];
  const put = (cell: number) => {
    sent.push(cell);
    return new Promise<void>((resolve, reject) =>
      gates.push(() => (failWith === undefined ? resolve() : reject(failWith))),
    );
  };
  return { put, sent, release: () => gates.splice(0).forEach((open) => open()) };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("the queue registry", () => {
  it("gives a game the same queue every time it is opened", () => {
    let made = 0;
    const registry = createQueueRegistry(() => {
      made++;
      return createInputQueue(async () => {});
    });

    expect(registry.queueFor("g")).toBe(registry.queueFor("g"));
    expect(registry.queueFor("h")).not.toBe(registry.queueFor("g"));
    expect(made).toBe(2);
  });

  it("never has two queues sending for one game at once", async () => {
    // Reopening the game while its first queue still drains must not start a
    // second one: two senders could land a cell's older value last.
    const server = heldPut();
    const registry = createQueueRegistry(() => createInputQueue(server.put));

    registry.queueFor("g").write(1, 5);
    registry.queueFor("g").write(2, 6);
    await settle();

    expect(server.sent).toEqual([1]); // the second waits behind the first
    server.release();
    await settle();
    server.release();
    await registry.queueFor("g").idle();
    expect(server.sent).toEqual([1, 2]);
  });

  it("replaces a queue that stopped", async () => {
    const closed = new ApiError("game_closed", 410, "…");
    const server = heldPut(closed);
    const registry = createQueueRegistry(() => createInputQueue(server.put));
    const first = registry.queueFor("g");
    first.write(1, 5);
    server.release();
    await first.idle();

    expect(first.stopped).toBe("closed");
    expect(registry.queueFor("g")).not.toBe(first);
  });

  it("reads the game only once every input typed for it has been sent", async () => {
    const server = heldPut();
    const registry = createQueueRegistry(() => createInputQueue(server.put));
    const order: string[] = [];
    registry.queueFor("g").write(1, 5);

    const loading = registry.loadAfterInputs("g", async () => {
      order.push("read");
      return GAME;
    });
    await settle();
    expect(order).toEqual([]);

    server.release();
    await expect(loading).resolves.toBe(GAME);
    expect(order).toEqual(["read"]);
  });

  it("reads a game nobody typed into at once", async () => {
    const registry = createQueueRegistry(() => createInputQueue(async () => {}));

    await expect(registry.loadAfterInputs("g", async () => GAME)).resolves.toBe(GAME);
  });

  it("is busy while any game has an input on its way, and not once it stopped", async () => {
    const server = heldPut();
    const registry = createQueueRegistry(() => createInputQueue(server.put));
    expect(registry.busy()).toBe(false);

    registry.queueFor("g").write(1, 5);
    expect(registry.busy()).toBe(true);
    server.release();
    await registry.queueFor("g").idle();
    expect(registry.busy()).toBe(false);

    const closing = heldPut(new ApiError("game_closed", 410, "…"));
    const closed = createQueueRegistry(() => createInputQueue(closing.put));
    closed.queueFor("g").write(1, 5);
    closing.release();
    await settle();
    expect(closed.busy()).toBe(false); // nothing left to lose: do not ask before closing
  });
});
