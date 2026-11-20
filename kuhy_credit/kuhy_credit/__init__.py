"""The shared kuhy credit for Python programs.

``credit_line()`` is the terminal form; :mod:`kuhy_credit.tk` holds the
Tkinter logo widget. The words and the link come from the generated
``_data`` module, which comes from ``credit.json``.
"""

from kuhy_credit._data import TEXT, URL


def credit_line() -> str:
    """The one-line credit for terminal programs: the text, then the URL."""
    return f"{TEXT} {URL}"


__all__ = ["TEXT", "URL", "credit_line"]
