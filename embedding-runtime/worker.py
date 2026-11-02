"""Offline, local-only E5 inference process; the caller owns authorization."""

import hashlib
import importlib.metadata
import json
import math
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer

MODEL_ID = "intfloat/multilingual-e5-base"
MODEL_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
WEIGHTS_SHA256 = "a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7"
TOKENIZER_FILES = {
    "config.json": "9dab198f24c8c0879e481cf7822005d5ecbceedbacb390ffafa594e28d31bac4",
    "tokenizer.json": "62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626",
    "tokenizer_config.json": "efb5c0d09722e5fe59a462cd2a9976ee216d55b037597d997cd3fe833216da15",
    "special_tokens_map.json": "06e405a36dfe4b9604f484f6a1e619af1a7f7d09e34a8555eb0b77b66318067f",
    "sentencepiece.bpe.model": "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865",
}
MODEL_CARD_SHA256 = "9d129cb0b912b55c7b5378f976a9c35ae4796c80466b659ad63930d8ca090fca"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


@contextmanager
def verified_snapshot(root):
    required = {
        **TOKENIZER_FILES,
        "model.safetensors": WEIGHTS_SHA256,
        "README.md": MODEL_CARD_SHA256,
    }
    allowed = set(required)
    if any(
        item.name not in allowed or item.is_symlink() or not item.is_file()
        for item in root.iterdir()
    ):
        raise ValueError("unexpected model directory content")
    with tempfile.TemporaryDirectory(prefix="rpb-e5-") as folder:
        target = Path(folder)
        try:
            for name, expected in required.items():
                source_fd = os.open(
                    root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                )
                checksum = hashlib.sha256()
                with (
                    os.fdopen(source_fd, "rb") as source,
                    (target / name).open("xb") as dest,
                ):
                    info = os.fstat(source.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 1_200_000_000:
                        raise ValueError("invalid model file")
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        checksum.update(block)
                        dest.write(block)
                if checksum.hexdigest() != expected:
                    raise ValueError("model file digest mismatch")
                (target / name).chmod(0o400)
            target.chmod(0o500)
            yield target
        finally:
            target.chmod(0o700)


def load(model_dir, expected_weights_digest):
    root = Path(model_dir).resolve(strict=True)
    if expected_weights_digest != WEIGHTS_SHA256:
        raise ValueError("model weights digest mismatch")
    tokenizer_digest = hashlib.sha256(
        json.dumps(TOKENIZER_FILES, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with verified_snapshot(root) as private:
        tokenizer = AutoTokenizer.from_pretrained(
            private, local_files_only=True, use_fast=True
        )
        model = AutoModel.from_pretrained(
            private, local_files_only=True, use_safetensors=True
        )
    model.eval()
    if model.config.hidden_size != 768 or not tokenizer.is_fast:
        raise ValueError("incompatible embedding model")
    runtime = hashlib.sha256()
    runtime.update(sys.version.encode())
    runtime.update(bytes.fromhex(digest(Path(__file__).resolve())))
    for distribution in sorted(
        importlib.metadata.distributions(),
        key=lambda item: item.metadata["Name"].lower(),
    ):
        runtime.update(
            f"{distribution.metadata['Name']}=={distribution.version}\n".encode()
        )
        for item in sorted(distribution.files or (), key=str):
            path = distribution.locate_file(item)
            if path.is_symlink() or not path.is_file():
                raise ValueError("runtime file unavailable")
            runtime.update(str(item).encode())
            runtime.update(bytes.fromhex(digest(path)))
    profile = {
        "model_id": MODEL_ID,
        "weights_revision": MODEL_REVISION,
        "weights_digest": expected_weights_digest,
        "tokenizer_revision": tokenizer_digest,
        "dimension": 768,
        "normalization": "l2",
        "distance": "cosine",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "runtime_digest": runtime.hexdigest(),
    }
    profile["profile_id"] = hashlib.sha256(
        json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return tokenizer, model, profile


def embed(tokenizer, model, kind, text):
    if (
        kind not in {"query", "passage"}
        or not isinstance(text, str)
        or not text.strip()
    ):
        raise ValueError("invalid input")
    encoded = tokenizer(kind + ": " + text, return_tensors="pt", truncation=False)
    if encoded["input_ids"].shape[1] > 512:
        raise ValueError("token limit exceeded")
    with torch.inference_mode():
        output = model(**encoded).last_hidden_state
        mask = encoded["attention_mask"].unsqueeze(-1)
        vector = (output * mask).sum(dim=1) / mask.sum(dim=1)
        norm = torch.linalg.vector_norm(vector, dim=1)
        if (
            not torch.isfinite(vector).all()
            or not torch.isfinite(norm).all()
            or norm.item() <= 0
        ):
            raise ValueError("invalid embedding")
        values = (vector / norm.unsqueeze(-1))[0].tolist()
    if len(values) != 768 or not all(math.isfinite(v) for v in values):
        raise ValueError("invalid embedding")
    return values


def main():
    try:
        tokenizer, model, profile = load(
            os.environ["RPB_EMBEDDING_MODEL_DIR"],
            os.environ["RPB_EMBEDDING_WEIGHTS_SHA256"],
        )
    except Exception:
        print(json.dumps({"error": "embedding dependency unavailable"}), flush=True)
        return 1
    print(json.dumps({"profile": profile}), flush=True)
    for line in sys.stdin:
        try:
            if len(line.encode()) > 1_000_000:
                raise ValueError("request too large")
            request = json.loads(line)
            if not isinstance(request, dict) or set(request) != {"kind", "text"}:
                raise ValueError("invalid request")
            if request["kind"] == "tokenize" and isinstance(request["text"], str):
                value = tokenizer(
                    request["text"],
                    add_special_tokens=False,
                    truncation=False,
                    return_offsets_mapping=True,
                )["offset_mapping"]
                length = len(
                    tokenizer("passage: " + request["text"], truncation=False)[
                        "input_ids"
                    ]
                )
                result = {"offsets": value, "passage_length": length}
            else:
                result = {
                    "vector": embed(tokenizer, model, request["kind"], request["text"])
                }
        except Exception:
            result = {"error": "embedding input or execution failed"}
        print(json.dumps(result, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
