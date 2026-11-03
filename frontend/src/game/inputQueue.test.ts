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

  it("lets a newer value of a failed cell wait its turn, behind what was typed before it", async () => {
    const server = fakePut([new TypeError("Failed to fetch")]);
    server.hold();
    const queue = createInputQueue(server.put, fakeSleep().sleep);

    queue.write(1, 1); // in flight, will be lost
    queue.write(2, 2);
    queue.write(1, 3); // the newer value of cell 1, queued after cell 2
    server.releaseAll();

    await queue.idle();
    expect(server.sent).toEqual([
      [1, 1],
      [2, 2],
      [1, 3],
    ]);
  });

  it("retries a lost input before the ones typed after it", async () => {
    const server = fakePut([new TypeError("Failed to fetch")]);
    const queue = createInputQueue(server.put, fakeSleep().sleep);

    queue.write(1, 1);
    queue.write(2, 2);

    await queue.idle();
    expect(server.sent).toEqual([
      [1, 1],
      [1, 1],
      [2, 2],
    ]);
  });

  it("starts the wait over once an input gets through", async () => {
    const offline = new TypeError("Failed to fetch");
    const server = fakePut([offline, undefined, offline]);
    const { sleep, asked } = fakeSleep();
    const queue = createInputQueue(server.put, sleep);

    queue.write(1, 1);
    queue.write(2, 2);

    await queue.idle();
    expect(asked).toEqual([1000, 1000]); // not 1 s, then 2 s
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
    expect(events.at(-1)).toEqual({ status: "saved", stopped: reason, clearRefused: false }); // nothing left waiting
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

/** Inputs and clears in one log, as the server would see them. */
function fakeLine(answers: unknown[] = []) {
  const log: string[] = [];
  const gates: Array<() => void> = [];
  let holding = false;
  const take = async (entry: string) => {
    log.push(entry);
    if (holding) await new Promise<void>((resolve) => gates.push(resolve));
    const answer = answers.shift();
    if (answer !== undefined) throw answer;
  };
  return {
    log,
    put: (cell: number, value: number | null) => take(`${cell}=${value}`),
    clearAll: () => take("clear"),
    hold: () => {
      holding = true;
    },
    releaseAll: async () => {
      holding = false;
      while (gates.length) {
        gates.shift()!();
        await Promise.resolve();
      }
    },
  };
}

describe("clearing the grid", () => {
  it("drops the inputs still waiting, and sends what comes after the clear after it", async () => {
    const line = fakeLine();
    line.hold();
    const queue = createInputQueue(line.put, fakeSleep().sleep, line.clearAll);

    queue.write(1, 1); // in flight
    queue.write(2, 2); // waiting: dropped, the grid is about to be emptied
    queue.clear();
    queue.write(3, 3); // after the clear
    await line.releaseAll();

    await expect(queue.idle()).resolves.toBe(true);
    expect(line.log).toEqual(["1=1", "clear", "3=3"]);
  });

  it("never retries an input from before the clear: it would undo it", async () => {
    const line = fakeLine([new TypeError("Failed to fetch")]);
    line.hold();
    const queue = createInputQueue(line.put, fakeSleep().sleep, line.clearAll);

    queue.write(1, 1); // in flight, will be lost...
    queue.clear(); // ...but the grid was cleared after it was typed
    await line.releaseAll();

    await queue.idle();
    expect(line.log).toEqual(["1=1", "clear"]);
  });

  it("retries a clear over the limit, still before what was written after it", async () => {
    const line = fakeLine([tooMany(2)]);
    const { sleep, asked } = fakeSleep();
    const queue = createInputQueue(line.put, sleep, line.clearAll);

    queue.clear();
    queue.write(5, 9);

    await queue.idle();
    expect(line.log).toEqual(["clear", "clear", "5=9"]);
    expect(asked).toEqual([2000]);
  });

  it("keeps a clear through a lost connection", async () => {
    const line = fakeLine([new TypeError("Failed to fetch")]);
    const queue = createInputQueue(line.put, fakeSleep().sleep, line.clearAll);

    queue.clear();

    await expect(queue.idle()).resolves.toBe(true);
    expect(line.log).toEqual(["clear", "clear"]);
  });

  it("is not idle until the clear is saved", async () => {
    const line = fakeLine();
    line.hold();
    const queue = createInputQueue(line.put, fakeSleep().sleep, line.clearAll);
    let idle = false;

    queue.clear();
    void queue.idle().then(() => (idle = true));
    await Promise.resolve();
    expect(idle).toBe(false);

    await line.releaseAll();
    await queue.idle();
    expect(idle).toBe(true);
  });

  it("says so when a clear is refused for good, and goes on with what came after", async () => {
    const line = fakeLine([new ApiError("forbidden_origin", 403, "…")]);
    const queue = createInputQueue(line.put, fakeSleep().sleep, line.clearAll);
    const events: QueueEvent[] = [];
    queue.subscribe((event) => events.push(event));

    queue.clear();
    queue.write(5, 9);

    expect(await queue.idle()).toBe(true);
    expect(line.log).toEqual(["clear", "5=9"]); // once: retrying cannot help
    expect(events.filter((event) => event.clearRefused)).toHaveLength(1);
    expect(events.at(-1)?.clearRefused).toBe(false);
  });

  it("says nothing of the kind about an input refused for good", async () => {
    const line = fakeLine([new ApiError("cell_is_given", 422, "…")]);
    const queue = createInputQueue(line.put, fakeSleep().sleep, line.clearAll);
    const events: QueueEvent[] = [];
    queue.subscribe((event) => events.push(event));

    queue.write(0, 1);

    await queue.idle();
    expect(events.some((event) => event.clearRefused)).toBe(false);
  });

  it("stops like an input when the game is over, and is ignored after", async () => {
    const line = fakeLine([closed]);
    const queue = createInputQueue(line.put, fakeSleep().sleep, line.clearAll);

    queue.clear();
    await expect(queue.idle()).resolves.toBe(false);
    queue.clear();

    expect(queue.stopped).toBe("closed");
    expect(line.log).toEqual(["clear"]);
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

  it("says nothing about a beat that comes back after it was stopped", async () => {
    vi.useFakeTimers();
    let refuse!: (error: unknown) => void;
    const beat = vi.fn(
      () =>
        new Promise<void>((_resolve, reject) => {
          refuse = reject;
        }),
    );
    const onStopped = vi.fn();
    const stop = startHeartbeat(beat, onStopped);

    await vi.advanceTimersByTimeAsync(HEARTBEAT_MS); // a beat goes out...
    stop(); // ...the page goes away...
    refuse(closed); // ...and the answer arrives after
    await vi.advanceTimersByTimeAsync(0);

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
