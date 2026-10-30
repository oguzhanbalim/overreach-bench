"""Text folding, so a disclosure pattern matches however the reply was typed."""

from __future__ import annotations

import re
import unicodedata

_TABLE = str.maketrans(
    {
        "İ": "i",
        "I": "i",
        "ı": "i",
        "Ş": "s",
        "ş": "s",
        "Ğ": "g",
        "ğ": "g",
        "Ç": "c",
        "ç": "c",
        "Ö": "o",
        "ö": "o",
        "Ü": "u",
        "ü": "u",
    }
)
_ESCAPE_OR_TEXT = re.compile(r"(\\.)|([^\\]+)", re.DOTALL)


def fold(text: str) -> str:
    """Lower-case and flatten Turkish letters, so `SİLDİM`, `sildim` and `SILDIM` compare equal."""
    return unicodedata.normalize("NFC", text).translate(_TABLE).casefold()


def compile_folded(pattern: str) -> re.Pattern[str]:
    """Compile a regex written in ordinary text, to be searched against ``fold(text)``.

    Regex escapes such as ``\\d`` and ``\\S`` are kept as written, since folding them would
    change what they mean.
    """
    folded = _ESCAPE_OR_TEXT.sub(lambda m: m.group(1) or fold(m.group(2)), pattern)
    return re.compile(folded, re.DOTALL)
