import { describe, expect, it } from "vitest";

import { ApiError, createClient, type Lock } from "./client";

// A fake server: each path answers from a queue of statuses (the last one
// repeats), and every request is recorded. Responses can be held back, so a
// test decides when "the network" answers.

interface Call {
  path: string;
  method: string;
  headers: Headers;
}

function json(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status });
}

const NOT_AUTHENTICATED = { error: { code: "not_authenticated", message: "Authentication required." } };

function fakeServer(routes: Record<string, number[]>) {
  const calls: Call[] = [];
  const held: Array<() => void> = [];
  let holding = false;
  let inFlight = 0;
  let maxInFlight = 0;

  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const path = String(input).replace(/^\/api/, "");
    calls.push({ path, method: init?.method ?? "GET", headers: new Headers(init?.headers) });
    const queue = routes[path] ?? [404];
    const status = queue.length > 1 ? queue.shift()! : queue[0]!;
    if (path === "/auth/refresh") maxInFlight = Math.max(maxInFlight, ++inFlight);
    if (holding) await new Promise<void>((resolve) => held.push(resolve));
    if (path === "/auth/refresh") inFlight--;
    if (status === 401) return json(401, NOT_AUTHENTICATED);
    if (status === 204) return new Response(null, { status: 204 });
    return json(status, { login: "ana", campus_name: "Berlin" });
  };

  return {
    fetch,
    calls,
    count: (path: string) => calls.filter((call) => call.path === path).length,
    /** Hold every response from now on, until `release`. */
    hold: () => {
      holding = true;
    },
    /** Answer held requests one at a time, oldest first, letting each answer's
     * consequences (a refresh, a retry) be sent and held in turn, until nothing
     * is left waiting. */
    release: async () => {
      for (;;) {
        await settle();
        const next = held.shift();
        if (!next) break;
        next();
      }
      holding = false;
    },
    get maxRefreshesInFlight() {
      return maxInFlight;
    },
  };
}

/** Let pending promise callbacks run. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

/** A mutex, as `navigator.locks` would be for every tab of the site. */
function sharedLock(): Lock {
  let tail: Promise<unknown> = Promise.resolve();
  return (task) => {
    const run = tail.then(task, task);
    tail = run.catch(() => undefined);
    return run;
  };
}

describe("a request answered 401", () => {
  it("refreshes once, then retries the request", async () => {
    const server = fakeServer({ "/users/me": [401, 200], "/auth/refresh": [200] });
    const api = createClient({ fetch: server.fetch, base: "/api" });

    await expect(api.getMe()).resolves.toEqual({ login: "ana", campus_name: "Berlin" });

    expect(server.calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /users/me",
      "POST /auth/refresh",
      "GET /users/me",
    ]);
  });

  it("shares one refresh among every request that hit a 401 meanwhile", async () => {
    // Five requests at once with an expired access token: one refresh, not five.
    const server = fakeServer({ "/users/me": [401, 401, 401, 401, 401, 200], "/auth/refresh": [200] });
    const api = createClient({ fetch: server.fetch, base: "/api" });

    const results = await Promise.all(Array.from({ length: 5 }, () => api.getMe()));

    expect(results).toHaveLength(5);
    expect(server.count("/auth/refresh")).toBe(1);
    expect(server.count("/users/me")).toBe(10);
  });

  it("signs out when the refresh fails, and retries nothing", async () => {
    const server = fakeServer({ "/users/me": [401], "/auth/refresh": [401] });
    const api = createClient({ fetch: server.fetch, base: "/api" });
    let signedOut = 0;
    api.onSignedOut(() => signedOut++);

    const error = await api.getMe().catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "not_authenticated", status: 401 });
    expect(signedOut).toBe(1);
    expect(server.count("/users/me")).toBe(1);
  });

  it("signs out when the retry is refused too, without refreshing again", async () => {
    // A refresh that worked, then a 401 anyway (the user was deleted, say): no loop.
    const server = fakeServer({ "/users/me": [401], "/auth/refresh": [200] });
    const api = createClient({ fetch: server.fetch, base: "/api" });
    let signedOut = 0;
    api.onSignedOut(() => signedOut++);

    await expect(api.getMe()).rejects.toMatchObject({ status: 401 });

    expect(server.count("/auth/refresh")).toBe(1);
    expect(server.count("/users/me")).toBe(2);
    expect(signedOut).toBe(1);
  });

  it("refreshes again later: a finished refresh is not reused", async () => {
    const server = fakeServer({ "/users/me": [401, 200, 401, 200], "/auth/refresh": [200] });
    const api = createClient({ fetch: server.fetch, base: "/api" });

    await api.getMe();
    await api.getMe();

    expect(server.count("/auth/refresh")).toBe(2);
  });

  it("is never retried on the session endpoints themselves", async () => {
    const server = fakeServer({ "/auth/logout": [401], "/auth/refresh": [200] });
    const api = createClient({ fetch: server.fetch, base: "/api" });

    await expect(api.logout()).rejects.toMatchObject({ status: 401 });

    expect(server.count("/auth/refresh")).toBe(0);
  });
});

describe("two tabs", () => {
  it("never refresh at the same time", async () => {
    // Each tab is its own client; navigator.locks is shared by the whole site.
    const server = fakeServer({ "/users/me": [401, 401, 200], "/auth/refresh": [200] });
    const lock = sharedLock();
    const first = createClient({ fetch: server.fetch, lock, base: "/api" });
    const second = createClient({ fetch: server.fetch, lock, base: "/api" });

    server.hold();
    const both = Promise.all([first.getMe(), second.getMe()]);
    await settle();
    await server.release();
    await both;

    expect(server.count("/auth/refresh")).toBe(2);
    expect(server.maxRefreshesInFlight).toBe(1);
  });

  it("would collide without the lock: the test can see it", async () => {
    // The control for the test above: with no lock, both refreshes overlap.
    const server = fakeServer({ "/users/me": [401, 401, 200], "/auth/refresh": [200] });
    const noLock: Lock = (task) => task();
    const first = createClient({ fetch: server.fetch, lock: noLock, base: "/api" });
    const second = createClient({ fetch: server.fetch, lock: noLock, base: "/api" });

    server.hold();
    const both = Promise.all([first.getMe(), second.getMe()]);
    await settle();
    await server.release();
    await both;

    expect(server.maxRefreshesInFlight).toBe(2);
  });
});

describe("answers", () => {
  it("turns the error envelope into an ApiError", async () => {
    const api = createClient({
      fetch: async () => json(409, { error: { code: "game_already_exists", message: "…" } }),
      base: "/api",
    });

    await expect(api.request("/games", { method: "POST", body: "{}" })).rejects.toMatchObject({
      code: "game_already_exists",
      status: 409,
    });
  });

  it("keeps the envelope's other fields: a 409 says which game to resume", async () => {
    const api = createClient({
      fetch: async () =>
        json(409, { error: { code: "game_already_exists", message: "…", game_id: "g-1" } }),
      base: "/api",
    });

    await expect(api.startGame("hard")).rejects.toMatchObject({ details: { game_id: "g-1" } });
  });

  it("reads a 429's Retry-After", async () => {
    const api = createClient({
      fetch: async () =>
        new Response(JSON.stringify({ error: { code: "too_many_requests", message: "…" } }), {
          status: 429,
          headers: { "Retry-After": "3" },
        }),
      base: "/api",
    });

    await expect(api.putCell("g", 4, 7)).rejects.toMatchObject({ retryAfterSeconds: 3 });
  });

  it("copes with a failure that has no envelope", async () => {
    const api = createClient({
      fetch: async () => new Response("<html>Bad Gateway</html>", { status: 502 }),
      base: "/api",
    });

    await expect(api.getHealth()).rejects.toMatchObject({ code: "unknown_error", status: 502 });
  });

  it("answers undefined for 204", async () => {
    const server = fakeServer({ "/auth/logout": [204] });
    const api = createClient({ fetch: server.fetch, base: "/api" });

    await expect(api.logout()).resolves.toBeUndefined();
  });

  it("sends cookies, and a JSON content type only with a body", async () => {
    const seen: RequestInit[] = [];
    const api = createClient({
      fetch: async (_input, init) => {
        seen.push(init ?? {});
        return new Response(null, { status: 204 });
      },
      base: "/api",
    });

    await api.request("/a");
    await api.request("/b", { method: "PUT", body: JSON.stringify({ value: 5 }) });

    expect(seen.map((init) => init.credentials)).toEqual(["include", "include"]);
    expect(seen.map((init) => new Headers(init.headers).get("Content-Type"))).toEqual([
      null,
      "application/json",
    ]);
  });
});
