import { useEffect, useState } from "react";

import { api, type ContinuingGame, type Today } from "../api/client";
import { difficultyLabel, formatDuration } from "../format";
import { type Slot, slotsOf, startOrResume } from "../home/home";
import { followLink, gamePath, navigate } from "../router";

/**
 * Five entries, always in the same places (Q7): the three difficulties of
 * today, then statistics and the leaderboard, inactive until Phase 8. No
 * cells here, ever: a grid is only seen once its game exists (Q13).
 */
export function HomePage() {
  const [today, setToday] = useState<Today | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    api.getToday().then(
      (loaded) => live && setToday(loaded),
      () => live && setFailed(true),
    );
    return () => {
      live = false;
    };
  }, []);

  if (failed) return <p className="status">Today's puzzles could not be loaded. Reload to try again.</p>;
  if (today === null) return <p className="status">Loading…</p>;

  return (
    <main className="home">
      <h1 className="play__title">Today's puzzles</h1>
      {today.continuing.length > 0 && <Continuing games={today.continuing} />}
      <ul className="slots">
        {slotsOf(today).map((slot) => (
          <li key={slot.difficulty}>
            <DifficultySlot slot={slot} />
          </li>
        ))}
        <li>
          <InactiveSlot title="My statistics" />
        </li>
        <li>
          <InactiveSlot title="Leaderboard" />
        </li>
      </ul>
    </main>
  );
}

function Continuing({ games }: { games: ContinuingGame[] }) {
  return (
    <section className="continuing" aria-label="Still open">
      {games.map((game) => (
        <p key={game.game_id} className="continuing__game">
          {difficultyLabel(game.difficulty)} from {game.date} is still open.{" "}
          <a href={gamePath(game.game_id)} onClick={(e) => followLink(e, gamePath(game.game_id))}>
            Continue it
          </a>
        </p>
      ))}
    </section>
  );
}

function DifficultySlot({ slot }: { slot: Slot }) {
  const [confirming, setConfirming] = useState(false);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const { puzzle } = slot;
  const title = difficultyLabel(slot.difficulty);

  async function start() {
    setStarting(true);
    setProblem(null);
    const outcome = await startOrResume(api.startGame, slot.difficulty);
    if ("gameId" in outcome) {
      navigate(gamePath(outcome.gameId));
      return;
    }
    setProblem(outcome.problem);
    setStarting(false);
  }

  if (puzzle === null) {
    return (
      <div className="slot slot--inactive">
        <h2 className="slot__title">{title}</h2>
        <p className="slot__text">Not available today.</p>
      </div>
    );
  }

  if (puzzle.status === "completed" && puzzle.game_id !== null) {
    return (
      <div className="slot slot--done">
        <h2 className="slot__title">{title}</h2>
        <p className="slot__text">
          Solved in {formatDuration(puzzle.official_seconds ?? 0)}
          {puzzle.active_seconds !== null && <> · {formatDuration(puzzle.active_seconds)} active</>}
        </p>
        <a
          className="button button--quiet"
          href={gamePath(puzzle.game_id)}
          onClick={(e) => followLink(e, gamePath(puzzle.game_id!))}
        >
          See the grid
        </a>
      </div>
    );
  }

  if (puzzle.status === "in_progress" && puzzle.game_id !== null) {
    return (
      <div className="slot">
        <h2 className="slot__title">{title}</h2>
        <p className="slot__text">In progress.</p>
        <a className="button" href={gamePath(puzzle.game_id)} onClick={(e) => followLink(e, gamePath(puzzle.game_id!))}>
          Continue
        </a>
      </div>
    );
  }

  // Not started. Starting shows the grid and starts its clock for good (D3),
  // so it takes a second, deliberate tap (D25).
  return (
    <div className="slot">
      <h2 className="slot__title">{title}</h2>
      {confirming ? (
        <>
          <p className="slot__text">The clock starts when the grid appears. There is no restart.</p>
          <div className="slot__actions">
            <button type="button" className="button" disabled={starting} onClick={start}>
              {starting ? "Starting…" : "Start the clock"}
            </button>
            <button
              type="button"
              className="button button--quiet"
              disabled={starting}
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="slot__text">Not started.</p>
          <button type="button" className="button" onClick={() => setConfirming(true)}>
            Play
          </button>
        </>
      )}
      {problem !== null && (
        <p className="slot__problem" role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}

function InactiveSlot({ title }: { title: string }) {
  return (
    <div className="slot slot--inactive" aria-disabled="true">
      <h2 className="slot__title">{title}</h2>
      <p className="slot__text">Coming later.</p>
    </div>
  );
}
