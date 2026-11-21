## Skeleton: Scans and simulation (scans)

Signal: single pass; O(1) extra space; walk an array, string or matrix and update a running answer.
Trap: the loop bound is i < length, never i <= length; a neighbour cell needs its bounds check before you read it.

```
// One pass over a list.
function scan(seq: number[]): number {
  let best: number = /* HOLE: start value that every real element beats */;
  for (let i = 0; i < seq.length; i++) {
    /* HOLE: update best from seq[i] */
  }
  return /* HOLE: what the loop leaves behind */;
}

// Row by row over a table of cells.
function sweep(cells: number[][]): number {
  const rows: number = cells.length;
  const cols: number = /* HOLE: width, safe when there are no rows */;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      /* HOLE: use cells[r][c]; check bounds before any neighbour */
    }
  }
  return /* HOLE: the final tally */;
}
```
