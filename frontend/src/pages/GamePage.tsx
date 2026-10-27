import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type GameView } from "../api/client";
import { difficultyLabel, formatDuration } from "../format";
import { type CheckOutcome, checkGrid, elapsedSeconds } from "../game/check";
import { type Grid, parseGrid, setCell } from "../game/grid";
import { startHeartbeat } from "../game/heartbeat";
import { createInputQueue, type QueueStatus, type StopReason } from "../game/inputQueue";
import { createQueueRegistry } from "../game/queues";
import { gameProblem } from "../home/home";
import { followLink, HOME_PATH } from "../router";
import { PlayPage } from "./PlayPage";

const queues = createQueueRegistry((gameId) =>
  createInputQueue((cell, value) => api.putCell(gameId, cell, value)),
);

// Closing the tab with an input not yet saved would lose it: ask first. For
// the whole tab, not one page, since a queue outlives its page.
window.addEventListener("beforeunload", (event) => {
  if (queues.busy()) event.preventDefault();
});

/**
 * A game as the server holds it (`GET /api/games/{id}`): resuming is reading
 * this, never anything the browser kept.
 */
export function GamePage({ gameId }: { gameId: string }) {
  const [game, setGame] = useState<GameView | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  // Only the latest load may show its answer: a slow one started earlier,
  // or by a page since left, is dropped.
  const generation = useRef(0);

  const load = useCallback(() => {
    const mine = ++generation.current;
    setGame(null);
    setProblem(null);
    queues.loadAfterInputs(gameId, api.getGame).then(
      (loaded) => generation.current === mine && setGame(loaded),
      (error: unknown) => generation.current === mine && setProblem(gameProblem(error)),
    );
  }, [gameId]);

  useEffect(() => {
    load();
    return () => {
      generation.current++;
    };
  }, [load]);

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

interface Solved {
  officialSeconds: number;
  activeSeconds: number;
}

function LiveGame({ game, onFinishedElsewhere }: { game: GameView; onFinishedElsewhere: () => void }) {
  const givens = useMemo(() => parseGrid(game.givens), [game.givens]);
  const [values, setValues] = useState<Grid>(() => parseGrid(game.state));
  const queue = useMemo(() => queues.queueFor(game.game_id), [game.game_id]);
  const [saving, setSaving] = useState<QueueStatus>(() => queue.status);
  const [stopped, setStopped] = useState<StopReason | null>(null);
  const [solved, setSolved] = useState<Solved | null>(() =>
    game.status === "completed"
      ? { officialSeconds: game.official_seconds ?? 0, activeSeconds: game.active_seconds }
      : null,
  );
  const [checking, setChecking] = useState(false);
  const [checked, setChecked] = useState<CheckOutcome | null>(null);
  const playing = solved === null && stopped === null;
  const clock = useClock(game.started_at, playing);
  const full = values.every((value) => value !== 0);

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

  const write = useCallback(
    (cell: number, value: number) => {
      setChecked(null); // an answer about the grid before this input is stale
      setValues((current) => setCell(current, givens, cell, value));
      queue.write(cell, value === 0 ? null : value);
    },
    [givens, queue],
  );

  async function check() {
    setChecking(true);
    const outcome = await checkGrid(
      () => queue.idle(),
      () => api.complete(game.game_id),
    );
    setChecking(false);
    if (outcome.kind === "solved") setSolved(outcome);
    else if (outcome.kind === "closed") setStopped("closed");
    else setChecked(outcome);
  }

  let note: string | null;
  if (solved !== null) {
    note =
      `Solved in ${formatDuration(solved.officialSeconds)}` +
      ` · ${formatDuration(solved.activeSeconds)} active.`;
  } else if (stopped !== null) note = STOPPED[stopped] ?? null;
  else note = SAVING[saving];

  return (
    <PlayPage
      title={`${difficultyLabel(game.difficulty)} · ${game.date}`}
      givens={givens}
      values={values}
      // Not while checking: an input then would make the answer about an
      // older grid than the one on screen.
      readOnly={!playing || checking}
      clock={clock}
      note={note}
      onWrite={write}
    >
      {playing && full && (
        <div className="check">
          <button type="button" className="button" disabled={checking} onClick={check}>
            {checking ? "Checking…" : "Check the grid"}
          </button>
          {checked?.kind === "wrong" && (
            <p className="check__answer" role="status">
              Not solved yet: something is wrong somewhere. Checked {checked.submissions}{" "}
              {checked.submissions === 1 ? "time" : "times"}.
            </p>
          )}
          {checked?.kind === "problem" && (
            <p className="check__answer check__answer--problem" role="alert">
              {checked.message}
            </p>
          )}
        </div>
      )}
    </PlayPage>
  );
}

/** The decorative clock, ticking once a second while the game is played.
 * The official time is the server's; this one is never sent (GAME_RULES.md §4). */
function useClock(startedAt: string, running: boolean): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return running ? formatDuration(elapsedSeconds(startedAt, now)) : null;
}

function BackLink() {
  return (
    <a className="back" href={HOME_PATH} onClick={(e) => followLink(e, HOME_PATH)}>
      ← Today's puzzles
    </a>
  );
}
