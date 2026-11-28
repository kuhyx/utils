#!/bin/bash
# The 250-line file cap is dropped (kuhy, 2026-11-27). This file stays so the
# shims in ~40 repos that exec it keep working; it accepts any arguments, prints
# nothing and exits 0. The checker library (file_length/) is kept, unused.
exit 0
