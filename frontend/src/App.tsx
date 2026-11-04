import { useCallback, useEffect, useState } from "react";

import { api } from "./api/client";
import { SessionBar } from "./components/SessionBar";
import { GamePage } from "./pages/GamePage";
import { HomePage } from "./pages/HomePage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { SignInPage } from "./pages/SignInPage";
import { followLink, HOME_PATH, PRIVACY_PATH, type Route, useRoute } from "./router";
import { deleteAccount, loadSession, type Session, takeLoginError } from "./session/session";

/** Who is here decides what is shown; for a signed-in user, the path does. */
export function App() {
  const route = useRoute();
  const [session, setSession] = useState<Session>({ kind: "loading" });
  // Read once; StrictMode may call this twice, so it must not touch the URL.
  const [loginError, setLoginError] = useState(() => takeLoginError(window.location.href));
  const [notice, setNotice] = useState<string | null>(null);

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

  // What the sign-in page cannot tell by itself, or else the bar's to report.
  const onDeleteAccount = useCallback(async () => {
    const deletion = await deleteAccount(api.deleteAccount);
    if (!deletion.signedOut) return deletion.message;
    setNotice(deletion.message);
    setSession({ kind: "signed_out" });
    return null;
  }, []);

  // Before anything about the session: it has to be readable before signing in.
  if (route.page === "privacy") return <PrivacyPage />;

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
      return <SignInPage error={loginError.message} notice={notice} />;
    case "signed_in":
      return (
        <>
          <SessionBar me={session.me} onSignOut={signOut} onDeleteAccount={onDeleteAccount} />
          <Page route={route} />
          <footer className="site-footer">
            <a href={PRIVACY_PATH} onClick={(e) => followLink(e, PRIVACY_PATH)}>
              Privacy
            </a>
          </footer>
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
    case "privacy": // shown by App, whoever is signed in
      return null;
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
