## Skeleton: Trees and graphs (trees)

Signal: tree, binary tree, search tree; depth-first or breadth-first search; graph, union-find, trie.
Trap: the empty subtree (null) is the base case of every depth-first walk; breadth-first search freezes the level size BEFORE its inner loop; a graph needs a visited set, a tree does not.

```
// Depth-first: answer from the two subtrees.
function dfs(cur: TreeNode | null): number {
  if (cur === null) { return /* HOLE: value for an empty subtree */; }
  const l: number = dfs(cur.left);
  const r: number = dfs(cur.right);
  return /* HOLE: combine l, r and cur.val */;
}

// Breadth-first: one level per outer turn.
const frontier: TreeNode[] = [/* HOLE: the start */];
while (frontier.length > 0) {
  const width: number = frontier.length;
  for (let i = 0; i < width; i++) {
    const cur: TreeNode = frontier.shift() as TreeNode;
    /* HOLE: visit cur; queue the children that exist */
  }
}
```
