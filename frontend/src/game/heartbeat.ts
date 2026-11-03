// "The player is here", every 60 seconds while a game is open (GAME_RULES.md
// §3). It drives active time and keeps a game alive past midnight, so a
// failed beat is not a reason to stop: the next one tries again. Only an
// answer that can never change stops it.
//
// The first beat comes a minute after opening, not on opening: reading a game
// is not activity (looking is not playing), and a beat on load would keep an
// idle game of yesterday open just by looking at it.

import { type StopReason, stopReasonOf } from "./inputQueue";

export const HEARTBEAT_MS = 60_000;

/** Starts beating; returns the function that stops it. */
export function startHeartbeat(
  beat: () => Promise<void>,
  onStopped: (reason: StopReason) => void,
  every: number = HEARTBEAT_MS,
): () => void {
  let stopped = false;
  const timer = setInterval(() => {
    beat().catch((error: unknown) => {
      const reason = stopReasonOf(error);
      if (stopped || reason === null) return;
      stop();
      onStopped(reason);
    });
  }, every);

  function stop() {
    stopped = true;
    clearInterval(timer);
  }
  return stop;
}
