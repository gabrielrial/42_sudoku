import { describe, expect, it } from "vitest";

import { gamePath, parseRoute } from "./router";

describe("parseRoute", () => {
  it.each([
    ["/", { page: "home" }],
    ["/games/3f2b", { page: "game", gameId: "3f2b" }],
    ["/games/3f2b/", { page: "game", gameId: "3f2b" }],
    ["/games/", { page: "not_found" }],
    ["/games/a/b", { page: "not_found" }],
    ["/games/%E0%A4%A", { page: "not_found" }], // a malformed escape does not throw
    ["/privacy", { page: "privacy" }],
    ["/privacy/more", { page: "not_found" }],
    ["/leaderboard", { page: "not_found" }],
  ])("%s", (pathname, route) => {
    expect(parseRoute(pathname)).toEqual(route);
  });

  it("reads back the path it builds, whatever the id holds", () => {
    for (const id of ["3f2b-11aa", "a/b", "?x=1"]) {
      expect(parseRoute(gamePath(id))).toEqual({ page: "game", gameId: id });
    }
  });
});
