"""The coach relay: one PC service behind the app's guided coaching UI.

``DOCS-coach-relay.md`` is the contract. The desktop app reaches it over a
loopback HTTP API (``http_api``), the phone through Firebase RTDB (``phone``);
both feed one paced serial lane (``lane``) into the session backend
(``coach``), which grades the five steps and runs the coaching chat.

Nothing here can reach the gate's ledger, credits or unlocks: the only
``leetcode_guard`` modules in the import closure are the read-only
submission probe and its client (``test_relay_boundary.py``).
"""
