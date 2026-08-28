"""Registry adapters: one module per ecosystem, all returning latest stable.

`http.py` is the only module in the whole package that opens a socket, so
offline behaviour and the reachability probe are testable in one place.
"""
