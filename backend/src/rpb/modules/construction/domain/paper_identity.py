"""D-CW-03: title-only automatic identity, without modifying source metadata."""

import unicodedata
from collections.abc import Iterable

from rpb.modules.construction.domain.runs import RunInputError


def normalized_paper_title(title: str) -> str:
    """Delete Unicode punctuation and lowercase; do not conflate mathematical symbols.

    No fuzzy matching, transliteration, whitespace collapsing or casefold expansion.
    Empty/whitespace-only results cannot identify a paper.
    """
    if not isinstance(title, str):
        raise RunInputError("paper title")
    result = "".join(c for c in title if not unicodedata.category(c).startswith("P")).lower()
    if not result.strip():
        raise RunInputError("empty normalized paper title")
    return result


def paper_title_groups(titles: Iterable[str]) -> list[list[int]]:
    """Return stable groups of source positions, retaining every duplicate's provenance.

    Positions, rather than merged metadata, leave source/content choice to the caller.
    This is automatic matching only; a saved human correction must take precedence.
    """
    groups: dict[str, list[int]] = {}
    for index, title in enumerate(titles):
        groups.setdefault(normalized_paper_title(title), []).append(index)
    return list(groups.values())
