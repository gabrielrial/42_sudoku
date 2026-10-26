import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type GameView } from "../api/client";
import { difficultyLabel, formatDuration } from "../format";
import { type Grid, parseGrid, setCell } from "../game/grid";
import { startHeartbeat } from "../game/heartbeat";
import { createInputQueue, type InputQueue, type QueueStatus, type StopReason } from "../game/inputQueue";
import { gameProblem } from "../home/home";
import { followLink, HOME_PATH } from "../router";
import { PlayPage } from "./PlayPage";

// One queue per game, for the life of the tab: leaving the page right after
// typing must not lose the input, so the queue outlives the page and drains
// on its own. Coming back waits for it before reading the board.
const queues = new Map<string, InputQueue>();

function queueFor(gameId: string): InputQueue {
  let queue = queues.get(gameId);
  if (queue === undefined || queue.stopped !== null) {
    queue = createInputQueue((cell, value) => api.putCell(gameId, cell, value));
    queues.set(gameId, queue);
  }
  return queue;
}

/**
 * A game as the server holds it (`GET /api/games/{id}`): resuming is reading
 * this, never anything the browser kept.
 */
export function GamePage({ gameId }: { gameId: string }) {
  const [game, setGame] = useState<GameView | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const load = useCallback(() => {
    let live = true;
    setGame(null);
    setProblem(null);
    // Inputs still on their way would be missing from what the server sends.
    void (queues.get(gameId)?.idle() ?? Promise.resolve(true))
      .then(() => api.getGame(gameId))
      .then(
        (loaded) => live && setGame(loaded),
        (error: unknown) => live && setProblem(gameProblem(error)),
      );
    return () => {
      live = false;
    };
  }, [gameId]);

  useEffect(load, [load]);

  if (problem !== null) {
    return (
      <div className="status">
        <p>{problem}</p>
        <BackLink />
      </div>
    );
  }
  if (game === null) return <p className="status">Loading…</p>;

  return (
    <>
      <nav className="game-nav">
        <BackLink />
      </nav>
      {/* A new game is a new board: nothing carried over from another. */}
      <LiveGame key={game.game_id} game={game} onFinishedElsewhere={load} />
    </>
  );
}

const SAVING: Record<QueueStatus, string> = {
  saved: "All inputs saved.",
  saving: "Saving…",
  waiting: "Saving… the server asked to slow down.",
  offline: "The server cannot be reached. Your inputs are kept and will be sent.",
};

const STOPPED: Partial<Record<StopReason, string>> = {
  closed: "This game was closed when its day ended. It can no longer be played.",
  not_found: "This game no longer exists.",
};

function LiveGame({ game, onFinishedElsewhere }: { game: GameView; onFinishedElsewhere: () => void }) {
  const givens = useMemo(() => parseGrid(game.givens), [game.givens]);
  const [values, setValues] = useState<Grid>(() => parseGrid(game.state));
  const queue = useMemo(() => queueFor(game.game_id), [game.game_id]);
  const [saving, setSaving] = useState<QueueStatus>(() => queue.status);
  const [stopped, setStopped] = useState<StopReason | null>(null);
  const completed = game.status === "completed";
  const playing = !completed && stopped === null;

  const onStopped = useCallback(
    (reason: StopReason) => {
      // Solved in another tab: what is shown here is out of date.
      if (reason === "completed") onFinishedElsewhere();
      else setStopped(reason);
    },
    [onFinishedElsewhere],
  );

  useEffect(
    () =>
      queue.subscribe((event) => {
        setSaving(event.status);
        if (event.stopped !== null) onStopped(event.stopped);
      }),
    [queue, onStopped],
  );

  useEffect(() => {
    if (!playing) return;
    return startHeartbeat(() => api.heartbeat(game.game_id), onStopped);
  }, [game.game_id, onStopped, playing]);

  // Closing the tab with inputs not yet saved would lose them: ask first.
  useEffect(() => {
    if (saving === "saved") return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [saving]);

  const write = useCallback(
    (cell: number, value: number) => {
      setValues((current) => setCell(current, givens, cell, value));
      queue.write(cell, value === 0 ? null : value);
    },
    [givens, queue],
  );

  let note: string | null;
  if (completed) note = `Solved in ${formatDuration(game.official_seconds ?? 0)}.`;
  else if (stopped !== null) note = STOPPED[stopped] ?? null;
  else note = SAVING[saving];

  return (
    <PlayPage
      title={`${difficultyLabel(game.difficulty)} · ${game.date}`}
      givens={givens}
      values={values}
      readOnly={!playing}
      note={note}
      onWrite={write}
    />
  );
}

function BackLink() {
  return (
    <a className="back" href={HOME_PATH} onClick={(e) => followLink(e, HOME_PATH)}>
      ← Today's puzzles
    </a>
  );
}
