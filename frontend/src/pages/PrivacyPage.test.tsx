import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CONTACT, CONTROLLER, PrivacyPage } from "./PrivacyPage";

describe("the privacy page", () => {
  const page = renderToStaticMarkup(<PrivacyPage />);

  it("says who is responsible and how to reach them", () => {
    expect(page).toContain(CONTROLLER);
    expect(page).toContain(`mailto:${CONTACT}`);
  });

  // What the page must not lose: each of these is a promise elsewhere in the
  // project, and a reader's only way to know it (DECISIONS.md Q8, D30, D31, D32).
  it.each([
    ["the record of moves", /Every move/],
    ["that notes are kept and recorded", /notes/],
    ["its retention, MOVE_LOG_DAYS", /30 days/],
    ["the session's lifetime, REFRESH_TOKEN_DAYS", /7 days/],
    ["the log rotation in docker-compose.yml", /three files of 10 MB/],
    ["the third party that sees the traffic", /ngrok/],
    ["how to delete an account", /delete your account/i],
  ])("mentions %s", (_, text) => {
    expect(page).toMatch(text);
  });
});
