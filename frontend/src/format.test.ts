import { expect, it } from "vitest";

import { formatDuration } from "./format";

it.each([
  [0, "0:00"],
  [7, "0:07"],
  [61, "1:01"],
  [1187, "19:47"],
  [3599, "59:59"],
  [3600, "1:00:00"],
  [3725, "1:02:05"],
  [-5, "0:00"],
])("%i seconds is %s", (seconds, text) => {
  expect(formatDuration(seconds)).toBe(text);
});
