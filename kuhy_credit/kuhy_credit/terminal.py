"""``kuhy-credit``: print the one-line credit. Opens nothing."""

from kuhy_credit import credit_line


def main() -> int:
    """Print the credit line; returns the exit code."""
    print(credit_line())
    return 0
