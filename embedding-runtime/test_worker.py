"""Embedding protocol bounds and normalization, with a deterministic model double."""

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from worker import embed, verified_snapshot


class Tokenizer:
    def __init__(self, size=4):
        self.size = size
        self.received = None

    def __call__(self, text, **kwargs):
        self.received = (text, kwargs)
        return {
            "input_ids": torch.ones((1, self.size), dtype=torch.int64),
            "attention_mask": torch.ones((1, self.size), dtype=torch.int64),
        }


class Model:
    def __init__(self, value=2.0):
        self.value = value

    def __call__(self, **encoded):
        class Output:
            pass

        output = Output()
        output.last_hidden_state = torch.full(
            (1, encoded["input_ids"].shape[1], 768), self.value
        )
        return output


class EmbeddingTests(unittest.TestCase):
    def test_prefix_and_l2_normalization(self):
        for kind in ("query", "passage"):
            tokenizer = Tokenizer()
            result = embed(tokenizer, Model(), kind, "中文 🙂")
            self.assertEqual(tokenizer.received[0], kind + ": 中文 🙂")
            self.assertFalse(tokenizer.received[1]["truncation"])
            self.assertEqual(len(result), 768)
            self.assertAlmostEqual(sum(v * v for v in result), 1, places=5)

    def test_no_truncation_or_invalid_vectors(self):
        self.assertEqual(len(embed(Tokenizer(512), Model(), "passage", "limit")), 768)
        with self.assertRaises(ValueError):
            embed(Tokenizer(513), Model(), "passage", "long")
        for value in (0.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                embed(Tokenizer(), Model(value), "passage", "text")
        with self.assertRaises(ValueError):
            embed(Tokenizer(), Model(), "passage", " ")

    def test_model_file_snapshot_rejects_extra_and_is_independent_of_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "config.json").write_bytes(b"config")
            (root / "model.safetensors").write_bytes(b"original")
            (root / "README.md").write_bytes(b"license: mit")
            files = {"config.json": hashlib.sha256(b"config").hexdigest()}
            weights = hashlib.sha256(b"original").hexdigest()
            with (
                patch("worker.TOKENIZER_FILES", files),
                patch("worker.WEIGHTS_SHA256", weights),
                patch(
                    "worker.MODEL_CARD_SHA256",
                    hashlib.sha256(b"license: mit").hexdigest(),
                ),
            ):
                (root / "added_tokens.json").write_text("{}")
                with self.assertRaises(ValueError):
                    with verified_snapshot(root):
                        pass
                (root / "added_tokens.json").unlink()
                with verified_snapshot(root) as private:
                    (root / "model.safetensors").write_bytes(b"replacement")
                    self.assertEqual(
                        (private / "model.safetensors").read_bytes(), b"original"
                    )

    def test_attention_mask_excludes_padding(self):
        class PaddedTokenizer(Tokenizer):
            def __call__(self, text, **kwargs):
                return {
                    "input_ids": torch.ones((1, 2), dtype=torch.int64),
                    "attention_mask": torch.tensor([[1, 0]]),
                }

        class PaddedModel:
            def __call__(self, **encoded):
                class Output:
                    pass

                output = Output()
                output.last_hidden_state = torch.zeros((1, 2, 768))
                output.last_hidden_state[0, 0, 0] = 2
                output.last_hidden_state[0, 1, 1] = 1000
                return output

        vector = embed(PaddedTokenizer(), PaddedModel(), "passage", "text")
        self.assertEqual(vector[0], 1.0)
        self.assertEqual(vector[1], 0.0)

    def test_replaced_model_file_fifo_does_not_block(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "config.json").write_bytes(b"config")
            (root / "model.safetensors").write_bytes(b"original")
            (root / "README.md").write_bytes(b"license")
            real_open = os.open

            def replace_before_open(path, flags, *args, **kwargs):
                if Path(path) == root / "config.json":
                    Path(path).unlink()
                    os.mkfifo(path)
                return real_open(path, flags, *args, **kwargs)

            with (
                patch("worker.TOKENIZER_FILES", {"config.json": hashlib.sha256(b"config").hexdigest()}),
                patch("worker.WEIGHTS_SHA256", hashlib.sha256(b"original").hexdigest()),
                patch("worker.MODEL_CARD_SHA256", hashlib.sha256(b"license").hexdigest()),
                patch("worker.os.open", side_effect=replace_before_open),
                self.assertRaises(ValueError),
            ):
                with verified_snapshot(root):
                    pass


if __name__ == "__main__":
    unittest.main()
