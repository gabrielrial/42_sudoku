import { useCallback, useEffect, useState } from "react";

import { api } from "./api/client";
import { SessionBar } from "./components/SessionBar";
import { GamePage } from "./pages/GamePage";
import { HomePage } from "./pages/HomePage";
import { SignInPage } from "./pages/SignInPage";
import { followLink, HOME_PATH, type Route, useRoute } from "./router";
import { loadSession, type Session, takeLoginError } from "./session/session";

/** Who is here decides what is shown; for a signed-in user, the path does. */
export function App() {
  const route = useRoute();
  const [session, setSession] = useState<Session>({ kind: "loading" });
  // Read once; StrictMode may call this twice, so it must not touch the URL.
  const [loginError, setLoginError] = useState(() => takeLoginError(window.location.href));

  const check = useCallback(() => {
    setSession({ kind: "loading" });
    void loadSession(api.getMe).then(setSession);
  }, []);

  useEffect(() => {
    // Shown once: a reload or a bookmark does not bring the message back.
    if (loginError.message !== null) window.history.replaceState(null, "", loginError.cleaned);
  }, [loginError]);

  // Signed in, an old failure is history: a later sign-out must not show it.
  useEffect(() => {
    if (session.kind === "signed_in") setLoginError((e) => ({ ...e, message: null }));
  }, [session.kind]);

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
          <Page route={route} />
        </>
      );
  }
}

function Page({ route }: { route: Route }) {
  switch (route.page) {
    case "home":
      return <HomePage />;
    case "game":
      // Another game is another page: nothing of the last one may show here.
      return <GamePage key={route.gameId} gameId={route.gameId} />;
    case "not_found":
      return (
        <div className="status">
          <p>There is nothing here.</p>
          <a className="back" href={HOME_PATH} onClick={(e) => followLink(e, HOME_PATH)}>
            ← Today's puzzles
          </a>
        </div>
      );
  }
}
