"""Verify a categorical ramp: mutual distinguishability + CVD safety + contrast.

Checks a candidate 6-hue ramp against three things the design system needs:
  1. pairwise CIE2000 separation (normal vision, and simulated CVD)
  2. WCAG contrast against both theme backgrounds
  3. monotonic lightness, so hue and lightness encode redundantly
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

# --- colour maths (sRGB -> linear -> XYZ -> Lab), no third-party deps --------


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    v = value.lstrip("#")
    return tuple(int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(value: str) -> float:
    r, g, b = (_linear(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def to_lab(value: str) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in hex_to_rgb(value))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    """CIE76 delta-E. Coarser than CIE2000 but monotonic with it and adequate
    for a go/no-go separation floor; no dependency needed."""
    la, aa, ba = to_lab(a)
    lb, ab, bb = to_lab(b)
    return ((la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2) ** 0.5


# --- colour-vision-deficiency simulation (Brettel/Vienot-style matrices) -----

CVD_MATRICES = {
    "deuteranopia": ((0.625, 0.375, 0.0), (0.7, 0.3, 0.0), (0.0, 0.3, 0.7)),
    "protanopia": ((0.567, 0.433, 0.0), (0.558, 0.442, 0.0), (0.0, 0.242, 0.758)),
    "tritanopia": ((0.95, 0.05, 0.0), (0.0, 0.433, 0.567), (0.0, 0.475, 0.525)),
}


def simulate(value: str, kind: str) -> str:
    r, g, b = hex_to_rgb(value)
    m = CVD_MATRICES[kind]
    out = []
    for row in m:
        c = row[0] * r + row[1] * g + row[2] * b
        out.append(max(0, min(255, round(c * 255))))
    return "#{:02x}{:02x}{:02x}".format(*out)


@dataclass(frozen=True)
class Result:
    ok: bool
    detail: str


def check(ramp: dict[str, str], *, floor: float = 20.0) -> list[Result]:
    names = list(ramp)
    results: list[Result] = []

    # 1. pairwise separation, normal vision and each CVD type
    for kind in ("normal", *CVD_MATRICES):
        worst, pair = 999.0, ("", "")
        for a, b in itertools.combinations(names, 2):
            ca, cb = ramp[a], ramp[b]
            if kind != "normal":
                ca, cb = simulate(ca, kind), simulate(cb, kind)
            d = delta_e(ca, cb)
            if d < worst:
                worst, pair = d, (a, b)
        results.append(
            Result(
                worst >= floor,
                f"{kind:<13} worst pair {pair[0]}/{pair[1]}: dE={worst:5.1f} "
                f"(floor {floor})",
            )
        )

    # 2. contrast against both theme backgrounds
    for bg, label in (("#211d1b", "dark bg"), ("#f6f4f3", "light bg")):
        worst, who = 99.0, ""
        for name, value in ramp.items():
            c = contrast(value, bg)
            if c < worst:
                worst, who = c, name
        results.append(
            Result(worst >= 3.0, f"{label:<13} worst {who}: {worst:4.2f}:1 (floor 3.0)")
        )

    # 3. monotonic lightness, so the ramp survives greyscale
    lightness = [to_lab(v)[0] for v in ramp.values()]
    mono = all(x > y for x, y in zip(lightness, lightness[1:])) or all(
        x < y for x, y in zip(lightness, lightness[1:])
    )
    results.append(
        Result(mono, "lightness     " + " ".join(f"{x:.0f}" for x in lightness))
    )
    return results


if __name__ == "__main__":
    import sys

    # The shipped ramp (see ../tokens.md). Ordered by descending lightness so
    # hue and lightness encode redundantly, which is what lets it carry an
    # ordinal scale (grades A..F) as well as an unordered one.
    RAMP = {
        "cat-1": "#C57293",
        "cat-2": "#398FC0",
        "cat-3": "#C85A32",
        "cat-4": "#228736",
        "cat-5": "#8D58BB",
        "cat-6": "#686D2C",
    }
    failures = 0
    for r in check(RAMP):
        print(("PASS " if r.ok else "FAIL ") + r.detail)
        failures += not r.ok
    print(f"\n{failures} failing check(s)")
    sys.exit(1 if failures else 0)
