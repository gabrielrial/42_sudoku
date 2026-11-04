import { useState } from "react";

import type { Me } from "../api/client";

interface SessionBarProps {
  me: Me;
  onSignOut: () => void;
  /** Resolves to `null` once signed out, or to what to tell the user otherwise. */
  onDeleteAccount: () => Promise<string | null>;
}

/** Who is signed in, and the ways out. */
export function SessionBar({ me, onSignOut, onDeleteAccount }: SessionBarProps) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  // A second tap, like starting a game (D25): it cannot be undone (D30).
  async function deleteAccount() {
    setDeleting(true);
    setProblem(null);
    setProblem(await onDeleteAccount());
    setDeleting(false);
  }

  return (
    <>
      <header className="session-bar">
        <span className="session-bar__who">
          {me.login} <span className="session-bar__campus">· {me.campus_name}</span>
        </span>
        <div className="session-bar__actions">
          <button
            type="button"
            className="button button--quiet"
            onClick={() => setConfirming(true)}
          >
            Delete account
          </button>
          <button
            type="button"
            className="button button--quiet"
            disabled={deleting}
            onClick={onSignOut}
          >
            Sign out
          </button>
        </div>
      </header>
      {confirming && (
        <section className="account-delete">
          <p className="account-delete__text">
            Delete your account and all your games? This cannot be undone. Signing in again
            starts a new account with nothing from this one.
          </p>
          {problem !== null && (
            <p className="account-delete__problem" role="alert">
              {problem}
            </p>
          )}
          <div className="slot__actions">
            <button type="button" className="button" disabled={deleting} onClick={deleteAccount}>
              {deleting ? "Deleting…" : "Delete my account"}
            </button>
            <button
              type="button"
              className="button button--quiet"
              disabled={deleting}
              onClick={() => {
                setConfirming(false);
                setProblem(null);
              }}
            >
              Cancel
            </button>
          </div>
        </section>
      )}
    </>
  );
}
