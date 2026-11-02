import pytest

from code_runner._compare import matches


@pytest.mark.parametrize(
    ("expected", "actual", "order", "want"),
    [
        ([0, 1], [0, 1], "exact", True),
        ([0, 1], [1, 0], "exact", False),
        ([0, 1], [1, 0], "any", True),
        ([0, 1], [1, 0, 2], "any", False),
        ([[1, 2], [3]], [[3], [1, 2]], "any", True),
        ([[1, 2], [3]], [[3], [2, 1]], "any", False),
        ([[1, 2], [3]], [[3], [2, 1]], "deep", True),
        ([[1, 2], [3]], [[3], [2, 9]], "deep", False),
        (3, 3.0, "exact", True),
        (0.1 + 0.2, 0.3, "exact", True),
        (2.0, 2.001, "exact", False),
        (True, 1, "exact", False),
        (1, True, "exact", False),
        (True, True, "exact", True),
        (None, None, "exact", True),
        (None, 0, "exact", False),
        ("ab", "ab", "exact", True),
        ("ab", "ba", "exact", False),
        ("1", 1, "exact", False),
        ({"a": [1]}, {"a": [1]}, "exact", True),
        ({"a": 1}, {"b": 1}, "exact", False),
        ({"a": 1}, {"a": 2}, "exact", False),
        (5, 5, "any", True),
        ([1], 1, "any", False),
        ([1.0, 2.0], [2.0, 1.0000001], "any", True),
    ],
)
def test_matches(expected: object, actual: object, order: str, *, want: bool) -> None:
    assert matches(expected, actual, order) is want


def test_unknown_order_is_refused() -> None:
    with pytest.raises(ValueError, match="order"):
        matches(1, 1, "sideways")
