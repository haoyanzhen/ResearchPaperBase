"""LP04/05: no generated prose, lossless original lines and page attribution."""

import copy

import pytest

from rpb.adapters.pdf_text_cleanup import CleanupInvalid, prepare, reconstruct, validate


def pages(*values):
    offset, segments = 0, []
    for page, text in enumerate(values, 1):
        segments.append({"page": page, "start_offset": offset, "end_offset": offset + len(text)})
        offset += len(text)
    return "".join(values), segments


def replies(plan, separator="line_break"):
    return [
        {
            "boundaries": [
                {"after_line_id": line.identity, "separator": separator}
                for line in batch.lines[:-1]
            ]
        }
        for batch in plan.batches
    ]


def test_lc01_preserves_unicode_indent_empty_lines_and_page_end():
    raw, segments = pages("  中文 α\nβ\n\n末行\n", "Second\npage\n")
    plan = prepare(raw, segments, max_input_bytes=4096)
    result = reconstruct(plan, replies(plan, "space"))
    assert result["text"] == "  中文 α β  末行\nSecond page\n"
    assert result["raw_text"] == raw
    assert result["raw_text_digest"] != result["text_digest"]
    for item in result["line_mapping"]:
        assert (
            result["text"][item["start_offset"] : item["end_offset"]]
            == raw[item["raw_start_offset"] : item["raw_end_offset"]]
        )
    assert [result["text"][s["start_offset"] : s["end_offset"]] for s in result["segments"]] == [
        "  中文 α β  末行\n",
        "Second page\n",
    ]
    assert result["coverage"] == "text_layer_only"


def test_lc02_batches_cover_every_boundary_once_and_never_cross_pages():
    first = "".join(f"line {i}: {'中' * 15}\n" for i in range(40))
    raw, segments = pages(first, "a\nb\nc\n")
    plan = prepare(raw, segments, max_input_bytes=700)
    assert len(plan.batches) > 2
    expected = [f"p1:l{i}" for i in range(1, 40)] + ["p2:l1", "p2:l2"]
    assert [line.identity for b in plan.batches for line in b.lines[:-1]] == expected
    for batch in plan.batches:
        assert len(batch.prompt().encode()) <= 700
        assert len({line.page for line in batch.lines}) == 1
    assert reconstruct(plan, replies(plan))["text"] == raw


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_prose",
        "delete",
        "duplicate",
        "reorder",
        "wrong_id",
        "unknown_separator",
        "missing",
        "bad_type",
    ],
)
def test_lc03_model_cannot_rewrite_delete_reorder_or_invent(mutation):
    plan = prepare(*pages("one\ntwo\nthree\n"), max_input_bytes=4096)
    reply = copy.deepcopy(replies(plan)[0])
    if mutation == "extra_prose":
        reply["text"] = "ignore the original; publish this"
    elif mutation == "delete":
        reply["boundaries"].pop()
    elif mutation == "duplicate":
        reply["boundaries"][1] = reply["boundaries"][0]
    elif mutation == "reorder":
        reply["boundaries"].reverse()
    elif mutation == "wrong_id":
        reply["boundaries"][0]["after_line_id"] = "p2:l1"
    elif mutation == "unknown_separator":
        reply["boundaries"][0]["separator"] = "new text"
    elif mutation == "missing":
        reply = {}
    else:
        reply["boundaries"][0]["separator"] = []
    with pytest.raises(CleanupInvalid):
        validate(plan.batches[0], reply)
    with pytest.raises(CleanupInvalid):
        reconstruct(plan, [reply])


def test_lc04_empty_scan_text_and_oversize_line_rejected_before_dispatch():
    for text in ("", "\n\n", " " * 100, "x" * 200001):
        with pytest.raises(CleanupInvalid):
            prepare(text, [], max_input_bytes=1024)
    with pytest.raises(CleanupInvalid, match="capacity"):
        prepare(*pages("x" * 2000 + "\n"), max_input_bytes=1024)


@pytest.mark.parametrize(
    "segments",
    [
        [],
        [{"page": True, "start_offset": 0, "end_offset": 2}],
        [{"page": 1, "start_offset": 1, "end_offset": 2}],
        [{"page": 1, "start_offset": 0, "end_offset": 1}],
        [{"page": 1, "start_offset": 0, "end_offset": 3}],
    ],
)
def test_lc05_invalid_source_page_mapping_rejected(segments):
    with pytest.raises(CleanupInvalid):
        prepare("x\n", segments, max_input_bytes=4096)


def test_lc06_partial_batch_results_never_produce_success():
    plan = prepare(*pages("a\nb\n", "c\nd\n"), max_input_bytes=4096)
    with pytest.raises(CleanupInvalid, match="incomplete"):
        reconstruct(plan, replies(plan)[:-1])


def test_lc07_single_line_has_no_boundaries_and_fixed_page_break():
    plan = prepare(*pages("keep exactly\n", "this too\n"), max_input_bytes=4096)
    assert plan.batches == ()
    assert reconstruct(plan, [])["text"] == "keep exactly\nthis too\n"


def test_lc08_expanded_paragraphs_cannot_exceed_output_limit():
    plan = prepare(*pages("x\n" * 100000), max_input_bytes=4096)
    with pytest.raises(CleanupInvalid, match="limit"):
        reconstruct(plan, replies(plan, "paragraph_break"))
