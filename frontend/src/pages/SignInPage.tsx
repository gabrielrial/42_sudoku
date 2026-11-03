import { LOGIN_URL } from "../api/client";

interface SignInPageProps {
  /** Why the last sign-in failed, if it did. */
  error: string | null;
}

/**
 * Signing in is a navigation to `/api/auth/login`, which goes on to 42 and
 * comes back here (API.md): a link, not a `fetch`.
 */
export function SignInPage({ error }: SignInPageProps) {
  return (
    <main className="sign-in">
      <h1 className="play__title">Sudoku 42</h1>
      <p className="sign-in__text">One puzzle a day for each difficulty, the same for everyone.</p>
      {error !== null && (
        <p className="sign-in__error" role="alert">
          {error}
        </p>
      )}
      <a className="button" href={LOGIN_URL}>
        Sign in with 42
      </a>
    </main>
  );
}
