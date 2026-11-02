"""Token-bounded slices retain offsets into the original immutable text."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class PassageTokenizer(Protocol):
    def offsets(self, text: str) -> Sequence[tuple[int, int]]:
        """Return untruncated passage-token Unicode codepoint spans, without special tokens."""

    def passage_length(self, text: str) -> int:
        """Count the exact encoded passage including prefix and special tokens."""


class ChunkingError(ValueError):
    """Tokenizer output cannot safely represent or encode the source text."""


@dataclass(frozen=True)
class TextSlice:
    start: int
    end: int


def split_text(text: str, tokenizer: PassageTokenizer) -> list[TextSlice]:
    """Split one source revision without normalizing or truncating its text."""
    if not text.strip():
        return []
    offsets = list(tokenizer.offsets(text))
    if not offsets:
        raise ChunkingError("nonempty text has no tokens")
    previous_start = -1
    for start, end in offsets:
        if not (0 <= start < end <= len(text)) or start < previous_start:
            raise ChunkingError("invalid token offsets")
        previous_start = start
    chunks: list[TextSlice] = []
    token_start = 0
    while token_start < len(offsets):
        token_end = min(token_start + 384, len(offsets))
        if token_end < len(offsets):
            # Prefer a paragraph or sentence boundary while guaranteeing progress.
            for i in range(token_end, token_start + 64, -1):
                between = text[offsets[i - 1][1] - 1 : offsets[i][0]]
                if any(mark in between for mark in ".!?。！？\n"):
                    token_end = i
                    break
        start = 0 if token_start == 0 else offsets[token_start][0]
        end = len(text) if token_end == len(offsets) else offsets[token_end - 1][1]
        while token_end > token_start and (
            len(tokenizer.offsets(text[start:end])) > 384
            or tokenizer.passage_length(text[start:end]) > 512
        ):
            token_end -= 1
            end = offsets[token_end - 1][1] if token_end > token_start else start
        if token_end <= token_start or end <= start:
            raise ChunkingError("passage exceeds embedding token limit")
        if text[start:end].strip():
            chunks.append(TextSlice(start, end))
        if token_end == len(offsets):
            break
        next_start = max(token_start + 1, token_end - 64)
        # Tokens can share a codepoint span (e.g. byte-level emoji tokens).
        while next_start < token_end and offsets[next_start][0] <= start:
            next_start += 1
        if next_start >= token_end:
            raise ChunkingError("token offsets cannot advance safely")
        token_start = next_start
    return chunks
