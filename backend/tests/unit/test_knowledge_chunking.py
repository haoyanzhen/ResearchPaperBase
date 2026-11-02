"""A09 chunk boundaries and failures, independent of model implementations."""

import re

import pytest

from rpb.modules.knowledge.domain.chunking import ChunkingError, split_text


class CharacterTokenizer:
    def offsets(self, text):
        return [(i, i + 1) for i in range(len(text))]

    def passage_length(self, text):
        return len(text) + 4


def test_original_unicode_offsets_overlap_and_complete_coverage():
    text = ("论文e\u0301🙂。研究\n" * 100) + "结尾"
    chunks = split_text(text, CharacterTokenizer())
    assert chunks[0].start == 0 and chunks[-1].end == len(text)
    assert all(0 < c.end - c.start <= 384 for c in chunks)
    assert all(
        a.start < b.start <= a.end and a.end - b.start <= 64 for a, b in zip(chunks, chunks[1:])
    )
    assert all(text[c.start : c.end] for c in chunks)


def test_empty_and_unrepresentable_input():
    assert split_text(" \n", CharacterTokenizer()) == []

    class Broken(CharacterTokenizer):
        def offsets(self, text):
            return []

    with pytest.raises(ChunkingError):
        split_text("正文", Broken())


def test_encoding_limit_cannot_be_silently_truncated():
    class TooLarge(CharacterTokenizer):
        def passage_length(self, text):
            return 513

    with pytest.raises(ChunkingError):
        split_text("重要文字", TooLarge())


def test_paragraph_break_between_non_whitespace_tokens_is_preferred():
    class WordTokenizer:
        def offsets(self, text):
            return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]

        def passage_length(self, text):
            return len(self.offsets(text)) + 4

    text = "word " * 300 + "\n" + "word " * 100
    chunks = split_text(text, WordTokenizer())
    assert chunks[0].end == len("word " * 299 + "word")
    assert chunks[-1].end == len(text)
