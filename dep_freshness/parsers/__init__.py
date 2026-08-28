"""Manifest parsers: read a file, emit `Dep`s. No network, no judgement.

Each parser is deliberately tolerant: an unpinned or malformed constraint
becomes a `Dep` with `pinned=None` so the gate reports it as a finding, rather
than crashing. A gate that dies on the input it exists to police is useless.
"""
