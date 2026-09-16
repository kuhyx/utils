import { describe, expect, it } from "vitest";

import { helper } from "./utils/helper";
import { mockUser } from "./mocks/user";

describe("helper", () => {
  // Violations: no-focused-tests, expect-expect.
  it.only("trims", () => {
    expect(helper(" a ")).toBe("a");
  });
  it("has no assertion", () => {
    helper(mockUser.name);
  });
});
