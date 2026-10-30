import copy
import json

import pytest

from rpb.adapters.pdf_cleanup_capacity import effective_config, plan_for_model
from rpb.adapters.pdf_text_cleanup import CleanupInvalid, reconstruct


def config(protocol="openai_chat", parameters=None, capacity=262144):
    return {
        "protocol": protocol,
        "parameters": parameters or {},
        "api_version": "",
        "model_context_windows": {"chosen": capacity},
    }


@pytest.mark.parametrize(
    "protocol", ["openai_chat", "openai_responses", "anthropic_messages", "gemini_content"]
)
def test_cap01_engine_default_does_not_mutate_frozen_configuration(protocol):
    original = config(protocol)
    before = copy.deepcopy(original)
    effective, output, defaulted = effective_config(original, "chosen")
    assert (output, defaulted) == (4096, True)
    assert effective["parameters"]["max_output_tokens"] == 4096
    assert original == before


@pytest.mark.parametrize(
    "parameters",
    [
        {"max_output_tokens": 8192},
        {"custom_params": {"max_tokens": 8192}},
        {"custom_params": {"max_completion_tokens": 8192}},
    ],
)
def test_cap02_explicit_output_and_aliases_are_unchanged(parameters):
    original = config(parameters=parameters)
    effective, output, defaulted = effective_config(original, "chosen")
    assert (output, defaulted) == (8192, False)
    assert effective == original


def test_cap03_default_precedes_anthropic_thinking_validation():
    original = config(
        "anthropic_messages",
        {"custom_params": {"thinking": {"type": "enabled", "budget_tokens": 1024}}},
    )
    assert effective_config(original, "chosen")[1:] == (4096, True)


def test_cap04_input_and_output_batches_preserve_all_lines():
    text = "".join("中" * 12 + str(i) + "\n" for i in range(200))
    cfg = config(parameters={"max_output_tokens": 512}, capacity=4096)
    plan = plan_for_model(
        text, [{"page": 1, "start_offset": 0, "end_offset": len(text)}], cfg, "chosen"
    )
    replies = []
    for batch in plan.batches:
        assert len(batch.prompt().encode()) + 512 + 2048 <= 4096
        reply = {
            "boundaries": [
                {"after_line_id": line.identity, "separator": "paragraph_break"}
                for line in batch.lines[:-1]
            ]
        }
        assert len(json.dumps(reply).encode()) <= 512 - 128
        replies.append(
            {"boundaries": [{**v, "separator": "line_break"} for v in reply["boundaries"]]}
        )
    assert len(plan.batches) > 1
    assert reconstruct(plan, replies)["text"] == text


@pytest.mark.parametrize(
    "capacity,output,text",
    [(4096, 4096, "a\nb\n"), (10000, 1, "a\nb\n"), (7000, 4096, "中" * 1000 + "\nb\n")],
)
def test_cap05_preflight_rejects_impossible_capacity_without_truncation(capacity, output, text):
    with pytest.raises(CleanupInvalid):
        plan_for_model(
            text,
            [{"page": 1, "start_offset": 0, "end_offset": len(text)}],
            config(parameters={"max_output_tokens": output}, capacity=capacity),
            "chosen",
        )


def test_cap06_real_mixed_pdf_and_existing_invisible_text_layer():
    import io

    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject
    from test_pdf_processing import sample

    from rpb.adapters.pdf_processing import parse_pdf

    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(sample("visible text"))).pages[0])
    image = DecodedStreamObject()
    image.set_data(bytes([255, 255, 255]))
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    image_ref = writer._add_object(image)
    blank = writer.add_blank_page(612, 792)
    blank[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): image_ref})}
    )
    content = DecodedStreamObject()
    content.set_data(b"q 612 0 0 792 0 0 cm /Im0 Do Q")
    blank[NameObject("/Contents")] = writer._add_object(content)
    ocr = writer.add_page(PdfReader(io.BytesIO(sample("existing OCR layer"))).pages[0])
    hidden = DecodedStreamObject()
    hidden.set_data(b"BT /F1 12 Tf 3 Tr 72 720 Td (existing OCR layer) Tj ET")
    ocr[NameObject("/Contents")] = writer._add_object(hidden)
    stream = io.BytesIO()
    writer.write(stream)
    parsed = parse_pdf(stream.getvalue())
    assert [part["page"] for part in parsed["segments"]] == [1, 3]
    assert "existing OCR layer" in parsed["text"]
    plan = plan_for_model(parsed["text"], parsed["segments"], config(), "chosen")
    assert plan.batches == ()  # one existing line per nonempty page
    result = reconstruct(plan, [])
    assert result["text"] == parsed["text"]
    assert result["coverage"] == "text_layer_only"
    assert [part["page"] for part in result["segments"]] == [1, 3]
