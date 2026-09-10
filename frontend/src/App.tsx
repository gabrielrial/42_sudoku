import { useEffect, useState } from "react";

import { getHealth } from "./api/client";

/** Placeholder shell. Real pages arrive in Phase 6. */
export function App() {
  const [status, setStatus] = useState<string>("checking…");

  useEffect(() => {
    getHealth()
      .then((h) => setStatus(`${h.status} — ${h.date}`))
      .catch(() => setStatus("unreachable"));
  }, []);

  return (
    <main>
      <h1>Sudoku 42</h1>
      <p>Backend: {status}</p>
    </main>
  );
}
