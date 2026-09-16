export function helper(value: string): string {
  return value.trim();
}

// Violation for Knip: never imported anywhere.
export function deadExport(): number {
  return 1;
}
