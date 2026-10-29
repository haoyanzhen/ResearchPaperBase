"""Scoring contracts preserve preview purity and independently editable judgments."""

import unittest

from test_api_contracts import SCHEMAS, SPEC_DATA, valid


class ScreeningContracts(unittest.TestCase):
    def test_preview_requires_csrf_but_no_idempotency_receipt(self):
        op = SPEC_DATA["paths"][
            "/projects/{project_id}/construction-runs/{run_id}/screening/action-preview"
        ]["post"]
        headers = {p["name"] for p in op["parameters"] if p["in"] == "header"}
        self.assertIn("X-CSRF-Token", headers)
        self.assertNotIn("Idempotency-Key", headers)
        meta = op["responses"]["200"]["content"]["application/json"]["schema"]["properties"]["meta"]
        self.assertEqual(meta, {"$ref": "#/components/schemas/Meta"})

    def test_manual_score_and_validity_are_independently_editable(self):
        for patch in [{"score": 0}, {"score": 7}, {"score": 10}, {"valid": False}, {"valid": True}]:
            self.assertTrue(
                valid(
                    "PaperScreeningPatch",
                    {"expected_revision": "r", "screening": patch | {"reason": "human judgment"}},
                )
            )
        for patch in [
            {"score": -1},
            {"score": 11},
            {"score": True},
            {"score": None},
            {"valid": None},
            {"valid": "true"},
            {"analysis": "not permitted"},
            {},
        ]:
            self.assertFalse(
                valid(
                    "PaperScreeningPatch",
                    {"expected_revision": "r", "screening": patch | {"reason": "human judgment"}},
                )
            )

    def test_scoring_task_does_not_claim_term_results_or_waiting_items(self):
        props = SCHEMAS["ScoringTaskView"]["properties"]
        self.assertEqual(props["stage"], {"const": "screening"})
        self.assertEqual(props["result_refs"], {"type": "array", "maxItems": 0})
        self.assertEqual(props["waiting_items"], {"type": "array", "maxItems": 0})
