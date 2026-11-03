// One input queue per game, for the life of the tab. Leaving a game right
// after typing must not lose the input, so a queue outlives its page and
// drains on its own; coming back waits for it before reading the board, or
// the board would miss what is still on its way. No React in here.

import type { GameView } from "../api/client";
import type { InputQueue } from "./inputQueue";

export interface QueueRegistry {
  /** The game's live queue, or a new one if it has none or its last stopped. */
  queueFor(gameId: string): InputQueue;
  /** The game as the server holds it, once every input already typed for it
   * has been sent. */
  loadAfterInputs(gameId: string, getGame: (gameId: string) => Promise<GameView>): Promise<GameView>;
  /** Some input of some game is not saved yet: closing the tab would lose it. */
  busy(): boolean;
}

export function createQueueRegistry(make: (gameId: string) => InputQueue): QueueRegistry {
  const queues = new Map<string, InputQueue>();
  return {
    queueFor(gameId) {
      let queue = queues.get(gameId);
      if (queue === undefined || queue.stopped !== null) {
        queue = make(gameId);
        queues.set(gameId, queue);
      }
      return queue;
    },
    async loadAfterInputs(gameId, getGame) {
      await queues.get(gameId)?.idle();
      return getGame(gameId);
    },
    busy() {
      return [...queues.values()].some((queue) => queue.status !== "saved");
    },
  };
}
