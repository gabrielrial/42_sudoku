// Two pages and a fallback; the History API is enough (PLAN.md, 6b: routing
// without a dependency). Vite's dev server answers every client path with
// index.html, so a reload or a shared link works; the production server must
// do the same (PLAN.md, Stage 7).

import { type MouseEvent, useMemo, useSyncExternalStore } from "react";

export type Route = { page: "home" } | { page: "game"; gameId: string } | { page: "not_found" };

export const HOME_PATH = "/";
export const gamePath = (gameId: string): string => `/games/${encodeURIComponent(gameId)}`;

export function parseRoute(pathname: string): Route {
  if (pathname === HOME_PATH) return { page: "home" };
  const game = /^\/games\/([^/]+)\/?$/.exec(pathname);
  if (game) {
    try {
      return { page: "game", gameId: decodeURIComponent(game[1]!) };
    } catch {
      return { page: "not_found" }; // a malformed %-escape
    }
  }
  return { page: "not_found" };
}

const NAVIGATED = "sudoku42:navigated";

export function navigate(path: string): void {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new Event(NAVIGATED));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange); // back and forward
  window.addEventListener(NAVIGATED, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(NAVIGATED, onChange);
  };
}

export function useRoute(): Route {
  const pathname = useSyncExternalStore(subscribe, () => window.location.pathname);
  return useMemo(() => parseRoute(pathname), [pathname]);
}

/** An `<a>`'s click, handled here unless the user asked for a new tab or window. */
export function followLink(event: MouseEvent<HTMLAnchorElement>, path: string): void {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return;
  }
  event.preventDefault();
  navigate(path);
}
