// Violations: no-explicit-any, no-non-null-assertion, parent-relative import,
// services importing from components (boundaries).
import { Button } from "../components/button";
import { helper } from "@/utils/helper";

export function fetchUser(id: string): any {
  const cache: Record<string, string | undefined> = {};
  const name = cache[id]!;
  return { id, name, label: helper(name), button: Button };
}
