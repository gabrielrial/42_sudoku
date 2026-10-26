import { useCallback, useEffect, useState } from "react";

import { api } from "./api/client";
import { SessionBar } from "./components/SessionBar";
import { PlayPage } from "./pages/PlayPage";
import { SignInPage } from "./pages/SignInPage";
import { loadSession, type Session, takeLoginError } from "./session/session";

/**
 * Who is here decides what is shown. The demo board stays the signed-in page
 * until the home page and the real game replace it (PLAN.md, 6b and 6c).
 */
export function App() {
  const [session, setSession] = useState<Session>({ kind: "loading" });
  // Read once; StrictMode may call this twice, so it must not touch the URL.
  const [loginError] = useState(() => takeLoginError(window.location.href));

  const check = useCallback(() => {
    setSession({ kind: "loading" });
    void loadSession(api.getMe).then(setSession);
  }, []);

  useEffect(() => {
    // Shown once: a reload or a bookmark does not bring the message back.
    if (loginError.message !== null) window.history.replaceState(null, "", loginError.cleaned);
  }, [loginError]);

  useEffect(() => {
    check();
    // Any request may find the session over, not only this first one.
    return api.onSignedOut(() => setSession({ kind: "signed_out" }));
  }, [check]);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
      setSession({ kind: "signed_out" });
    } catch {
      setSession({ kind: "unreachable" });
    }
  }, []);

  switch (session.kind) {
    case "loading":
      return <p className="status">Loading…</p>;
    case "unreachable":
      return (
        <div className="status">
          <p>The server cannot be reached right now.</p>
          <button type="button" className="button" onClick={check}>
            Try again
          </button>
        </div>
      );
    case "signed_out":
      return <SignInPage error={loginError.message} />;
    case "signed_in":
      return (
        <>
          <SessionBar me={session.me} onSignOut={signOut} />
          <PlayPage />
        </>
      );
  }
}
