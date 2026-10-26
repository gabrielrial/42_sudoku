import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { backoff, createInputQueue, type QueueEvent } from "./inputQueue";
import { HEARTBEAT_MS, startHeartbeat } from "./heartbeat";

type Put = (cell: number, value: number | null) => Promise<void>;

/** A fake server for inputs: answers in order from `answers` (then 204s),
 * records what it was sent, and can hold its answers back. */
function fakePut(answers: unknown[] = []) {
  const sent: Array<[number, number | null]> = [];
  let inFlight = 0;
  let maxInFlight = 0;
  const gates: Array<() => void> = [];
  let holding = false;

  const put: Put = async (cell, value) => {
    sent.push([cell, value]);
    maxInFlight = Math.max(maxInFlight, ++inFlight);
    if (holding) await new Promise<void>((resolve) => gates.push(resolve));
    inFlight--;
    const answer = answers.shift();
    if (answer !== undefined) throw answer;
  };

  return {
    put,
    sent,
    get maxInFlight() {
      return maxInFlight;
    },
    hold: () => {
      holding = true;
    },
    releaseOne: () => gates.shift()?.(),
    releaseAll: () => {
      holding = false;
      gates.splice(0).forEach((open) => open());
    },
  };
}

/** A sleep that returns at once and remembers how long it was asked for. */
function fakeSleep() {
  const asked: number[] = [];
  const sleep = async (ms: number) => {
    asked.push(ms);
  };
  return { sleep, asked };
}

const tooMany = (seconds: number) => new ApiError("too_many_requests", 429, "…", {}, seconds);
const closed = new ApiError("game_closed", 410, "…");

describe("the input queue", () => {
  it("sends every input, in the order typed, one at a time", async () => {
    const server = fakePut();
    const queue = createInputQueue(server.put);

    queue.write(3, 5);
    queue.write(4, 6);
    queue.write(10, null);

    await expect(queue.idle()).resolves.toBe(true);
    expect(server.sent).toEqual([
      [3, 5],
      [4, 6],
      [10, null],
    ]);
    expect(server.maxInFlight).toBe(1);
  });

  it("sends a cell written again before its turn once, with its last value", async () => {
    const server = fakePut();
    server.hold();
    const queue = createInputQueue(server.put);

    queue.write(1, 1); // in flight
    queue.write(2, 2); // waiting...
    queue.write(2, 3); // ...and replaced before its turn
    queue.write(2, 4);
    server.releaseAll();

    await queue.idle();
    expect(server.sent).toEqual([
      [1, 1],
      [2, 4],
    ]);
  });

  it("sends a cell written again while in flight a second time: the last value lands", async () => {
    const server = fakePut();
    server.hold();
    const queue = createInputQueue(server.put);

    queue.write(1, 1); // in flight
    queue.write(1, 2);
    server.releaseAll();

    await queue.idle();
    expect(server.sent).toEqual([
      [1, 1],
      [1, 2],
    ]);
  });

  it("waits out a 429 for as long as Retry-After says, then sends the same input", async () => {
    const server = fakePut([tooMany(3)]);
    const { sleep, asked } = fakeSleep();
    const queue = createInputQueue(server.put, sleep);
    const statuses: string[] = [];
    queue.subscribe((event) => statuses.push(event.status));

    queue.write(7, 9);
    queue.write(8, 1);

    await expect(queue.idle()).resolves.toBe(true);
    expect(asked).toEqual([3000]);
    expect(server.sent).toEqual([
      [7, 9],
      [7, 9],
      [8, 1],
    ]);
    expect(statuses).toContain("waiting");
    expect(statuses.at(-1)).toBe("saved");
  });

  it("does not resend an old value after a 429 if the cell was written again", async () => {
    const server = fakePut([tooMany(1)]);
    server.hold();
    const queue = createInputQueue(server.put, fakeSleep().sleep);

    queue.write(7, 9); // in flight, will be refused
    queue.write(7, 2); // the newer value
    server.releaseAll();

    await queue.idle();
    expect(server.sent).toEqual([
      [7, 9],
      [7, 2],
    ]);
  });

  it("keeps an input through a lost connection, retrying with a growing wait", async () => {
    const offline = new TypeError("Failed to fetch");
    const down = new ApiError("unknown_error", 502, "Bad Gateway");
    const server = fakePut([offline, down, offline]);
    const { sleep, asked } = fakeSleep();
    const queue = createInputQueue(server.put, sleep);
    const statuses: string[] = [];
    queue.subscribe((event) => statuses.push(event.status));

    queue.write(0, 4);

    await expect(queue.idle()).resolves.toBe(true);
    expect(server.sent).toHaveLength(4); // three failures, then saved
    expect(asked).toEqual([1000, 2000, 4000]);
    expect(statuses).toContain("offline");
  });

  it("drops an input the server refuses for good, and goes on", async () => {
    const given = new ApiError("cell_is_given", 409, "…");
    const server = fakePut([given]);
    const queue = createInputQueue(server.put, fakeSleep().sleep);

    queue.write(0, 4);
    queue.write(1, 5);

    await expect(queue.idle()).resolves.toBe(true);
    expect(server.sent).toEqual([
      [0, 4],
      [1, 5],
    ]);
  });

  it.each([
    ["game_closed", 410, "closed"],
    ["game_completed", 409, "completed"],
    ["game_not_found", 404, "not_found"],
    ["not_authenticated", 401, "signed_out"],
  ])("stops for good on %s", async (code, status, reason) => {
    const server = fakePut([new ApiError(code, status, "…")]);
    const queue = createInputQueue(server.put, fakeSleep().sleep);
    const events: QueueEvent[] = [];
    queue.subscribe((event) => events.push(event));

    queue.write(0, 4);
    queue.write(1, 5);

    await expect(queue.idle()).resolves.toBe(false);
    queue.write(2, 6); // ignored: the game is over
    expect(server.sent).toEqual([[0, 4]]);
    expect(queue.stopped).toBe(reason);
    expect(events.at(-1)?.stopped).toBe(reason);
    await expect(queue.idle()).resolves.toBe(false);
  });

  it("is idle at once when nothing was written", async () => {
    await expect(createInputQueue(fakePut().put).idle()).resolves.toBe(true);
  });

  it("is not idle while the last input is still in flight", async () => {
    const server = fakePut();
    server.hold();
    const queue = createInputQueue(server.put);
    let idle = false;

    queue.write(0, 1);
    void queue.idle().then(() => (idle = true));
    await Promise.resolve();
    expect(idle).toBe(false);

    server.releaseAll();
    await queue.idle();
    expect(idle).toBe(true);
  });
});

describe("backoff", () => {
  it("doubles from one second and stops at thirty", () => {
    expect([1, 2, 3, 4, 5, 6, 7].map(backoff)).toEqual([
      1000, 2000, 4000, 8000, 16000, 30000, 30000,
    ]);
  });
});

describe("the heartbeat", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("beats every minute, and not on opening: looking is not playing", async () => {
    vi.useFakeTimers();
    const beat = vi.fn(async () => {});
    const stop = startHeartbeat(beat, () => {});

    expect(beat).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(HEARTBEAT_MS - 1);
    expect(beat).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(beat).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(HEARTBEAT_MS * 2);
    expect(beat).toHaveBeenCalledTimes(3);

    stop();
    await vi.advanceTimersByTimeAsync(HEARTBEAT_MS * 5);
    expect(beat).toHaveBeenCalledTimes(3);
  });

  it("keeps beating after a beat that failed: the next one may get through", async () => {
    vi.useFakeTimers();
    const failures = [new TypeError("Failed to fetch"), tooMany(30)];
    const beat = vi.fn(async () => {
      const failure = failures.shift();
      if (failure) throw failure;
    });
    const onStopped = vi.fn();
    startHeartbeat(beat, onStopped);

    await vi.advanceTimersByTimeAsync(HEARTBEAT_MS * 3);

    expect(beat).toHaveBeenCalledTimes(3);
    expect(onStopped).not.toHaveBeenCalled();
  });

  it("stops, and says why, when the game is over", async () => {
    vi.useFakeTimers();
    const beat = vi.fn(async () => {
      throw closed;
    });
    const onStopped = vi.fn();
    startHeartbeat(beat, onStopped);

    await vi.advanceTimersByTimeAsync(HEARTBEAT_MS * 4);

    expect(beat).toHaveBeenCalledTimes(1);
    expect(onStopped).toHaveBeenCalledWith("closed");
  });
});
