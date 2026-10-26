import { useEffect, useState } from "react";

import { api, type GameView } from "../api/client";
import { difficultyLabel, formatDuration } from "../format";
import { gameProblem } from "../home/home";
import { followLink, HOME_PATH } from "../router";
import { PlayPage } from "./PlayPage";

/**
 * A game as the server holds it (`GET /api/games/{id}`): resuming is reading
 * this, never anything the browser kept. Inputs are not sent yet; the
 * playing loop is PLAN.md 6c.
 */
export function GamePage({ gameId }: { gameId: string }) {
  const [game, setGame] = useState<GameView | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setGame(null);
    setProblem(null);
    api.getGame(gameId).then(
      (loaded) => live && setGame(loaded),
      (error: unknown) => live && setProblem(gameProblem(error)),
    );
    return () => {
      live = false;
    };
  }, [gameId]);

  const back = (
    <a className="back" href={HOME_PATH} onClick={(e) => followLink(e, HOME_PATH)}>
      ← Today's puzzles
    </a>
  );

  if (problem !== null) {
    return (
      <div className="status">
        <p>{problem}</p>
        {back}
      </div>
    );
  }
  if (game === null) return <p className="status">Loading…</p>;

  const completed = game.status === "completed";
  return (
    <>
      <nav className="game-nav">{back}</nav>
      <PlayPage
        // A new game is a new board: no selection or cells carried over.
        key={game.game_id}
        title={`${difficultyLabel(game.difficulty)} · ${game.date}`}
        givens={game.givens}
        state={game.state}
        readOnly={completed}
        note={completed ? `Solved in ${formatDuration(game.official_seconds ?? 0)}.` : null}
      />
    </>
  );
}
