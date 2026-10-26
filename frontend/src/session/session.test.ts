import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { loadSession, takeLoginError } from "./session";

const ANA = { login: "ana", campus_name: "Berlin" };

describe("loadSession", () => {
  it("is signed in when /users/me answers", async () => {
    await expect(loadSession(async () => ANA)).resolves.toEqual({ kind: "signed_in", me: ANA });
  });

  it("is signed out on a 401: nobody is, which is not an error", async () => {
    const refused = async () => {
      throw new ApiError("not_authenticated", 401, "Authentication required.");
    };

    await expect(loadSession(refused)).resolves.toEqual({ kind: "signed_out" });
  });

  it.each([
    ["a server error", new ApiError("unknown_error", 502, "Bad Gateway")],
    ["no network", new TypeError("Failed to fetch")],
  ])("is unreachable on %s, never signed out", async (_name, failure) => {
    // Showing the sign-in button here would send a signed-in user to 42 for nothing.
    const failing = async () => {
      throw failure;
    };

    await expect(loadSession(failing)).resolves.toEqual({ kind: "unreachable" });
  });
});

describe("takeLoginError", () => {
  it("finds nothing in an ordinary URL, and leaves it alone", () => {
    expect(takeLoginError("http://localhost:5173/")).toEqual({
      message: null,
      cleaned: "http://localhost:5173/",
    });
  });

  it.each([
    ["invalid_state", /expired or was already used/],
    ["access_denied", /declined access on 42/],
    ["provider_error", /42 could not be reached/],
    ["no_primary_campus", /no primary campus/],
    ["too_many_requests", /Too many sign-in attempts/],
  ])("has its own message for %s", (code, message) => {
    expect(takeLoginError(`http://localhost:5173/?login_error=${code}`).message).toMatch(message);
  });

  it("has a generic message for a code it does not know", () => {
    // Anyone can put anything in a URL; it is never shown as it came.
    const { message } = takeLoginError("http://x/?login_error=%3Cscript%3E");

    expect(message).toBe("Signing in did not work. Please try again.");
  });

  it("ignores names an object inherits", () => {
    expect(takeLoginError("http://x/?login_error=constructor").message).toBe(
      "Signing in did not work. Please try again.",
    );
  });

  it("removes the code from the URL and keeps the rest", () => {
    expect(takeLoginError("http://x/play?login_error=access_denied&a=1#top").cleaned).toBe(
      "/play?a=1#top",
    );
    expect(takeLoginError("http://x/?login_error=access_denied").cleaned).toBe("/");
  });
});
