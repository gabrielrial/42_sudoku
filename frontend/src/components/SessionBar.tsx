import type { Me } from "../api/client";

interface SessionBarProps {
  me: Me;
  onSignOut: () => void;
}

/** Who is signed in, and the way out. */
export function SessionBar({ me, onSignOut }: SessionBarProps) {
  return (
    <header className="session-bar">
      <span className="session-bar__who">
        {me.login} <span className="session-bar__campus">· {me.campus_name}</span>
      </span>
      <button type="button" className="button button--quiet" onClick={onSignOut}>
        Sign out
      </button>
    </header>
  );
}
