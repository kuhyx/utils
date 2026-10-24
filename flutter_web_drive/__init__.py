"""Headless, LLM-friendly driver for Flutter web apps over the Chrome DevTools Protocol.

A long-lived headless chromium runs as a ``systemd-run --user`` unit; every
verb attaches over CDP, does one thing through Flutter's semantics tree, and
exits with a code that is the verdict. See README.md.
"""
