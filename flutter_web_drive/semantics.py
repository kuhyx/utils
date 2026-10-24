"""Flutter web's semantics DOM: the only addressable view of a canvas-rendered app.

Flutter paints to a canvas, so widgets are found through the accessibility
mirror it writes as ``[id^=flt-semantic-node-]`` elements (``flt-semantics``,
but also ``h1``-``h6`` for headings). The mirror is off until something asks
for it; clicking ``flt-semantics-placeholder`` is how a screen reader does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flutter_web_drive.errors import DriveError

# Turns semantics on (idempotent). 'on' | 'clicked' | 'missing' (Flutter not booted).
ENABLE_JS = """(() => {
  if (document.querySelector('[id^="flt-semantic-node-"]')) return 'on';
  const p = document.querySelector('flt-semantics-placeholder');
  if (!p) return 'missing';
  p.click();
  return 'clicked';
})()"""

FLUTTER_READY_JS = (
    "!!document.querySelector('flt-semantics-placeholder, flt-semantics-host')"
)

FOCUS_JS = """(() => {
  const e = document.activeElement;
  return !!e && (e.tagName === 'INPUT' || e.tagName === 'TEXTAREA' || e.isContentEditable);
})()"""

VIEWPORT_JS = "[innerWidth, innerHeight]"

# One record per semantics node. A node's own label is its aria-label, else its
# direct text / <span> children (not descendant nodes': those are listed on
# their own). value = field value, aria-valuenow or aria-description.
# Password fields report asterisks, never their value.
COLLECT_JS = """(() => {
  const flagsOf = (e) => {
    const a = (n) => e.getAttribute(n);
    const f = [];
    if (a('aria-current') && a('aria-current') !== 'false') f.push('current');
    if (a('aria-selected') === 'true') f.push('selected');
    if (a('aria-checked') === 'true') f.push('checked');
    if (a('aria-checked') === 'mixed') f.push('mixed');
    if (a('aria-pressed') === 'true') f.push('pressed');
    if (a('aria-expanded') === 'true') f.push('expanded');
    if (a('aria-disabled') === 'true' || e.disabled) f.push('disabled');
    if (document.activeElement === e) f.push('focused');
    return f;
  };
  return [...document.querySelectorAll('[id^="flt-semantic-node-"]')].map((e) => {
    const field = e.matches('input,textarea')
      ? e : e.querySelector(':scope > input, :scope > textarea');
    let own = '';
    for (const c of e.childNodes) {
      // Plain Text widgets render as a bare text node or a scaled <span>.
      if (c.nodeType === 3) own += c.textContent;
      else if (c.tagName === 'SPAN' && !c.id.startsWith('flt-semantic-node-')) own += c.textContent;
    }
    const flags = flagsOf(e);
    if (field && field !== e) for (const x of flagsOf(field)) if (!flags.includes(x)) flags.push(x);
    const r = e.getBoundingClientRect();
    const fieldLabel = field && (field.getAttribute('aria-label') || field.placeholder);
    let value = e.getAttribute('aria-valuenow') || e.getAttribute('aria-description') || '';
    if (field) value = field.type === 'password' ? '*'.repeat(field.value.length) : field.value;
    return {
      id: Number(e.id.slice(18)), tag: e.tagName.toLowerCase(),
      role: e.getAttribute('role') || (field ? 'textbox' : ''),
      label: (e.getAttribute('aria-label') || fieldLabel || own || '').trim(), value,
      x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
      tappable: e.hasAttribute('flt-tappable'), flags,
    };
  });
})()"""

# Called as `${IMAGE_STATS_FN}("<base64 png>")`: decodes the screenshot in the
# page and returns size, distinct colours (capped) and luminance stddev.
IMAGE_STATS_FN = """(async (b64) => {
  const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const bmp = await createImageBitmap(new Blob([bin], {type: 'image/png'}));
  const g = new OffscreenCanvas(bmp.width, bmp.height).getContext('2d');
  g.drawImage(bmp, 0, 0);
  const d = g.getImageData(0, 0, bmp.width, bmp.height).data;
  const seen = new Set();
  let s = 0, s2 = 0;
  for (let i = 0; i < d.length; i += 4) {
    const l = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
    s += l; s2 += l * l;
    if (seen.size < 100000) seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
  }
  const n = d.length / 4, mean = s / n;
  return {w: bmp.width, h: bmp.height, colours: seen.size,
          stddev: Math.sqrt(Math.max(0, s2 / n - mean * mean))};
})"""

HINT_LIMIT = 12


@dataclass(frozen=True)
class Node:
    """One semantics node with its on-screen rectangle (CSS pixels)."""

    id: int
    tag: str
    role: str
    label: str
    value: str
    x: float
    y: float
    w: float
    h: float
    tappable: bool
    flags: tuple[str, ...]

    @property
    def lines(self) -> tuple[str, ...]:
        """The label split on newlines (Flutter joins merged labels with them)."""
        return tuple(part.strip() for part in self.label.split("\n"))

    @property
    def center(self) -> tuple[float, float]:
        """Where a pointer should land to hit this node."""
        return (self.x + self.w / 2, self.y + self.h / 2)

    @property
    def one_line(self) -> str:
        """Label with newlines shown as ' | '."""
        return " | ".join(self.lines)

    @property
    def interesting(self) -> bool:
        """Worth listing in the compact tree: not a bare layout container."""
        return bool(self.role or self.label or self.value or self.tappable)


def parse_nodes(raw: Any) -> list[Node]:
    """Typed nodes from COLLECT_JS output."""
    if not isinstance(raw, list):
        raise DriveError(
            "semantics", f"unexpected semantics payload: {type(raw).__name__}"
        )
    return [
        Node(
            id=int(r["id"]),
            tag=str(r["tag"]),
            role=str(r["role"]),
            label=str(r["label"]),
            value=str(r["value"]),
            x=float(r["x"]),
            y=float(r["y"]),
            w=float(r["w"]),
            h=float(r["h"]),
            tappable=bool(r["tappable"]),
            flags=tuple(str(f) for f in r["flags"]),
        )
        for r in raw
    ]


def matches(node: Node, target: str, *, contains: bool = False) -> bool:
    """Exact: the whole label, its `tree` form ("a | b") or one line. Contains: substring, any case."""
    if contains:
        return target.lower() in node.label.lower()
    return target in (node.label, node.one_line, *node.lines)


def find(nodes: list[Node], target: str, *, contains: bool = False) -> list[Node]:
    """Matching nodes, tappable ones first, otherwise in document order."""
    hits = [n for n in nodes if matches(n, target, contains=contains)]
    return sorted(hits, key=lambda n: not n.tappable)


def in_row(nodes: list[Node], anchor: str, *, contains: bool = False) -> list[Node]:
    """Nodes whose vertical center lies inside the row of the node labelled ``anchor``.

    For "the Mark-read button of Chapter 5" style lookups. No anchor: [].
    """
    hits = find(nodes, anchor, contains=contains)
    if not hits:
        return []
    top, bottom = hits[0].y, hits[0].y + hits[0].h
    return [n for n in nodes if n.id != hits[0].id and top <= n.center[1] <= bottom]


def describe(node: Node) -> str:
    """``#id role "label" = "value" [tags] @x,y wxh`` on one line."""
    out = f'#{node.id} {node.role or node.tag} "{node.one_line}"'
    if node.value:
        out += f' = "{node.value}"'
    tags = (["tap"] if node.tappable else []) + list(node.flags)
    if tags:
        out += f" [{','.join(tags)}]"
    return out + f" @{node.x:g},{node.y:g} {node.w:g}x{node.h:g}"


def format_tree(
    nodes: list[Node],
    *,
    filt: str | None = None,
    show_all: bool = False,
    row: str | None = None,
) -> str:
    """Compact listing, one node per line; ``filt`` matches label, role or value; ``row`` scopes to a row."""
    if not nodes:
        return "(no semantics nodes)"
    shown = [
        n for n in (in_row(nodes, row) if row else nodes) if show_all or n.interesting
    ]
    if filt:
        needle = filt.lower()
        shown = [
            n for n in shown if needle in f"{n.label}\n{n.role}\n{n.value}".lower()
        ]
    if not shown:
        return "(no matching semantics nodes)"
    return "\n".join(describe(n) for n in shown)


def hint(nodes: list[Node]) -> str:
    """Tappable labels on screen, for 'not found' messages an agent can act on."""
    labels = [f'"{n.one_line}"' for n in nodes if n.tappable and n.label]
    if not labels:
        return "(no tappable nodes)"
    more = ", ..." if len(labels) > HINT_LIMIT else ""
    return ", ".join(labels[:HINT_LIMIT]) + more
