import { followLink, HOME_PATH } from "../router";

export const CONTROLLER = "Gabriel Rial";
export const CONTACT = "sudoku42@yahoo.com";
export const UPDATED = "2026-11-04";

/**
 * What is kept about a player, why and for how long (DECISIONS.md Q8). Public:
 * it has to be readable before signing in. It describes what the code does, so
 * a change to what is stored, who sees it or for how long changes this page too.
 */
export function PrivacyPage() {
  return (
    <main className="privacy">
      <a className="back" href={HOME_PATH} onClick={(e) => followLink(e, HOME_PATH)}>
        ← Back
      </a>
      <h1 className="play__title">Privacy</h1>
      <p>Last updated {UPDATED}.</p>

      <h2>Who is responsible</h2>
      <p>
        Sudoku 42 is a personal project run by {CONTROLLER}, who decides what happens to your data.
        Write to <a href={`mailto:${CONTACT}`}>{CONTACT}</a> about anything on this page.
      </p>

      <h2>What is kept</h2>
      <ul>
        <li>
          <strong>From your 42 account,</strong> when you sign in: your 42 user id, your login, and
          your primary campus. Not your email, your phone, your picture, your 42 password or your 42
          access token.
        </li>
        <li>
          <strong>Your games:</strong> the grid as it stands, when you started, finished and were
          last active, your active time, and how many times you checked the grid.
        </li>
        <li>
          <strong>Every move:</strong> each digit you enter or remove, each time you clear the grid,
          and each check with its answer, all with the time.
        </li>
        <li>
          <strong>Your session:</strong> two cookies that keep you signed in, a third that protects
          the sign-in itself for ten minutes, and a hash of your session token.
        </li>
        <li>
          <strong>Logs:</strong> the IP address, address visited, time and result of each request,
          and warnings from the application. IP addresses are also held in memory, to limit sign-in
          attempts.
        </li>
      </ul>
      <p>
        These cookies are needed for the site to work. There is no advertising, no analytics and no
        tracking, and nothing is sold. Other players cannot see your games.
      </p>

      <h2>Why, and on what legal basis</h2>
      <ul>
        <li>
          To give you the game you signed in for, and keep your games: performing what you asked for
          (Article 6(1)(b) GDPR).
        </li>
        <li>
          To find out what went wrong when something fails, and to keep the site safe: the record of
          moves, the logs and the limits. This is a legitimate interest (Article 6(1)(f) GDPR), which
          you can object to.
        </li>
      </ul>

      <h2>Who else sees it</h2>
      <ul>
        <li>
          <strong>42</strong> handles the sign-in and tells this site who you are. Its own privacy
          terms apply to your 42 account.
        </li>
        <li>
          <strong>ngrok</strong> connects this site to the internet, and the secure connection ends
          on its servers. So every request passes through ngrok readable, cookies included. Its
          documentation gives 24 hours for its traffic inspector; what else it keeps is ngrok&apos;s
          to answer for. It may handle this outside the EU. Its program, on the machine running this
          site, also shows the operator recent requests in full.
        </li>
        <li>Nobody else, unless the law requires it.</li>
      </ul>

      <h2>How long</h2>
      <ul>
        <li>
          <strong>Account and games:</strong> until you delete your account.
        </li>
        <li>
          <strong>Moves:</strong> 30 days, or until you delete your account if that comes first.
        </li>
        <li>
          <strong>Session:</strong> it stops working after 7 days without use. Its record goes when
          you sign out or delete your account.
        </li>
        <li>
          <strong>Logs:</strong> until overwritten. Each part of the site keeps three files of 10 MB,
          and the oldest is replaced when they fill, so there is no fixed number of days.
        </li>
        <li>
          <strong>Backups:</strong> there are none for now. If that changes, this page will say so.
        </li>
      </ul>

      <h2>Your rights</h2>
      <p>
        You can ask for a copy of your data, have it corrected or erased, limit its use, object to
        it, and take it elsewhere. Write to the address above. You can also complain to your data
        protection authority.
      </p>
      <p>
        <strong>To delete your account,</strong> use the button next to “Sign out”. Your account,
        games, moves and sessions leave the database at once. What cannot be picked out by person
        stays until it is overwritten: IP addresses and addresses visited in the logs, and whatever
        ngrok holds. Signing in again makes a new account, with nothing from the old one.
      </p>
    </main>
  );
}
