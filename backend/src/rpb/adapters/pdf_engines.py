"""Static extraction engine registry; each request selects exactly one engine.

Engines return text, page offsets and a diagnostic through the isolated runner.
LLM extraction is a later design target and is deliberately not registered.
"""

# The child sees neither application credentials nor application/Project storage.
EXTRACT = """
import json, resource, sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
from pypdf import PdfReader
result = {"reason": "corrupt_content", "text": None, "segments": []}
try:
    reader = PdfReader(sys.argv[1], strict=True)
    if reader.is_encrypted:
        result["reason"] = "encrypted_content"
    elif len(reader.pages) > 2000:
        result["reason"] = "safety_limit"
    else:
        text, segments = "", []
        for number, page in enumerate(reader.pages, 1):
            value = page.extract_text()
            if not value.strip(): continue
            value += chr(10)
            if len(text) + len(value) > 200000:
                raise OverflowError()
            segments.append({"start_offset": len(text), "end_offset": len(text)+len(value),
                             "page": number})
            text += value
        result = {"reason": None if text.strip() else "no_usable_text",
                  "text": text or None, "segments": segments}
except (MemoryError, OverflowError):
    result = {"reason": "safety_limit", "text": None, "segments": []}
except Exception:
    pass
Path(sys.argv[2]).write_text(json.dumps(result))
"""


ENGINES = {"pypdf": EXTRACT}


def available_engines() -> tuple[str, ...]:
    return tuple(ENGINES)


def extraction_script(engine: str) -> str:
    if engine not in ENGINES:
        raise ValueError("Unknown PDF extraction engine")
    return ENGINES[engine]
