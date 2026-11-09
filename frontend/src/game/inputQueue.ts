// Every input reaches the server, in order, and none is lost to a rate limit
// or a dropped connection (GAME_RULES.md §3: every input is sent, validated
// and persisted). No React in here.
//
// One request at a time, in the order typed: the server locks the game row
// per input anyway. Every digit is sent, even one rewritten before its turn:
// placing a digit takes it out of the notes of its row, column and box (D33),
// which the screen has already done, so the server has to see each digit to
// end up with the same notes. Notes have no such effect on other cells: notes
// for a cell written again with nothing else in between are sent once, with
// their last value, which spares the rate limit (a burst of 10, refilled at
// one a second, D22) when several are tapped in a row.
//
// Clearing the grid (D27) goes through the same line: whatever was waiting
// is dropped, the grid being about to be emptied anyway, and whatever is
// written afterwards is sent after the clear. An old digit can never land
// on a grid cleared after it was typed.

import { ApiError } from "../api/client";

/** Why the queue stopped for good. */
export type StopReason = "closed" | "completed" | "not_found" | "signed_out";

export type QueueStatus =
  | "saved" // nothing waiting
  | "saving"
  | "waiting" // over the rate limit, until Retry-After has passed
  | "offline"; // the server did not answer; retrying

export interface QueueEvent {
  status: QueueStatus;
  stopped: StopReason | null;
  /** The server refused a clear for good: it still holds the digits that the
   * screen, having emptied them at once, no longer shows. */
  clearRefused: boolean;
}

export interface InputQueue {
  /** `value` 1-9, or `null` to clear. */
  write(cell: number, value: number | null): void;
  /** Every digit noted in the cell, replacing what was there (D33). */
  writeNotes(cell: number, digits: readonly number[]): void;
  /** Empty every cell the player filled. */
  clear(): void;
  /** Resolves once everything written so far is saved: `true`, or `false`
   * if the queue stopped first. */
  idle(): Promise<boolean>;
  subscribe(listener: (event: QueueEvent) => void): () => void;
  readonly status: QueueStatus;
  readonly stopped: StopReason | null;
}

const STOPS: Record<string, StopReason> = {
  game_closed: "closed",
  game_completed: "completed",
  game_not_found: "not_found",
  not_authenticated: "signed_out",
};

/** The answers that end a game's traffic for good; `null` for any other. */
export function stopReasonOf(error: unknown): StopReason | null {
  return error instanceof ApiError && Object.hasOwn(STOPS, error.code) ? STOPS[error.code]! : null;
}

/** Waits after a lost connection: 1 s, 2 s, 4 s… never more than 30 s. */
export const backoff = (failures: number): number => Math.min(30_000, 1000 * 2 ** (failures - 1));

type Entry =
  | { kind: "digit"; cell: number; value: number | null }
  | { kind: "notes"; cell: number; digits: readonly number[] };
// `digits` is replaced in place when the same cell's notes are written again.

export function createInputQueue(
  put: (cell: number, value: number | null) => Promise<void>,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  clearAll: () => Promise<void> = async () => {},
  putNotes: (cell: number, digits: readonly number[]) => Promise<void> = async () => {},
): InputQueue {
  // In sending order.
  let pending: Entry[] = [];
  // A clear asked for and not yet saved. It goes before every cell waiting:
  // asking for it dropped the rest, so those were all written after it.
  let clearing = false;
  // How many clears were asked for: an input taken before the latest one is
  // never retried, or it would undo the clear.
  let clears = 0;
  const listeners = new Set<(event: QueueEvent) => void>();
  let idleWaiters: Array<(saved: boolean) => void> = [];
  let status: QueueStatus = "saved";
  let stopped: StopReason | null = null;
  let running = false;

  function emit(next: QueueStatus, clearRefused = false) {
    status = next;
    const event = { status, stopped, clearRefused };
    listeners.forEach((listener) => listener(event));
  }

  function settleIdle(saved: boolean) {
    const waiters = idleWaiters;
    idleWaiters = [];
    waiters.forEach((resolve) => resolve(saved));
  }

  async function run() {
    if (running) return;
    running = true;
    let failures = 0;
    while (stopped === null && (clearing || pending.length > 0)) {
      let send: () => Promise<void>;
      let retry: () => void;
      const sendingClear = clearing;
      if (clearing) {
        clearing = false;
        send = clearAll;
        retry = () => {
          clearing = true;
        };
      } else {
        const entry = pending.shift()!;
        const taken = clears;
        send = () =>
          entry.kind === "digit"
            ? put(entry.cell, entry.value)
            : putNotes(entry.cell, entry.digits);
        // Back at the head: whatever was typed after it is still sent after it.
        retry = () => {
          if (clears === taken) pending.unshift(entry);
        };
      }
      emit("saving");
      try {
        await send();
        failures = 0;
      } catch (error) {
        const reason = stopReasonOf(error);
        if (reason !== null) {
          stopped = reason;
          pending = [];
          break;
        }
        if (error instanceof ApiError && error.status === 429) {
          retry();
          emit("waiting");
          await sleep(1000 * (error.retryAfterSeconds ?? 1));
          continue;
        }
        if (error instanceof ApiError && error.status < 500) {
          // Refused for good, and retrying cannot change the answer. An input
          // (a given, an invalid value) the interface never sends: dropped. A
          // clear it does send, so whoever shows the grid has to hear of it.
          if (sendingClear) emit("saving", true);
          continue;
        }
        // No answer, or the server failed: the input is not lost, only late.
        retry();
        failures += 1;
        emit("offline");
        await sleep(backoff(failures));
      }
    }
    running = false;
    // Nothing is waiting either way: a stopped queue dropped what it had,
    // which the game being over made pointless. `stopped` says which it is.
    emit("saved");
    settleIdle(stopped === null);
  }

  return {
    write(cell, value) {
      if (stopped !== null) return;
      pending.push({ kind: "digit", cell, value });
      void run();
    },
    writeNotes(cell, digits) {
      if (stopped !== null) return;
      const last = pending.at(-1);
      if (last?.kind === "notes" && last.cell === cell) last.digits = digits;
      else pending.push({ kind: "notes", cell, digits });
      void run();
    },
    clear() {
      if (stopped !== null) return;
      pending = [];
      clears += 1;
      clearing = true;
      void run();
    },
    idle() {
      if (stopped !== null) return Promise.resolve(false);
      if (!running && !clearing && pending.length === 0) return Promise.resolve(true);
      return new Promise((resolve) => idleWaiters.push(resolve));
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    get status() {
      return status;
    },
    get stopped() {
      return stopped;
    },
  };
}
