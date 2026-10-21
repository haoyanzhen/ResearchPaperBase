import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_api_contracts import SPEC, COVERAGE, check, compatibility
from jsonschema import Draft202012Validator, FormatChecker

SPEC_DATA = json.loads(SPEC.read_text())
SCHEMAS = SPEC_DATA['components']['schemas']


def valid(name, value):
    # Internal refs use the same OpenAPI component root; validation remains JSON Schema 2020-12.
    schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
              '$ref': '#/components/schemas/' + name, 'components': {'schemas': SCHEMAS}}
    return Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(value)


class ContractTests(unittest.TestCase):
    def test_published_contract(self):
        check(SPEC_DATA, json.loads(COVERAGE.read_text()))

    def test_request_unknown_and_null_rejected(self):
        self.assertTrue(valid('ProjectWrite', {'name': 'Study'}))
        self.assertFalse(valid('ProjectWrite', {'name': 'Study', 'owner_id': 'forged'}))
        self.assertFalse(valid('ProjectWrite', {'name': None}))
        self.assertFalse(valid('ProjectWrite', {'name': '   '}))

    def test_patch_requires_revision_and_does_not_default(self):
        self.assertFalse(valid('ProjectPatch', {'name': 'Study'}))
        self.assertTrue(valid('ProjectPatch', {'expected_revision': 'r1'}))
        self.assertNotIn('default', SCHEMAS['ProjectPatch']['properties']['description'])

    def test_create_defaults_do_not_contaminate_patch(self):
        self.assertEqual(SCHEMAS['ProjectWrite']['properties']['description']['default'], '')
        self.assertEqual(SCHEMAS['ProjectWrite']['properties']['research_scope']['default'], '')
        self.assertTrue(SCHEMAS['SourceWrite']['properties']['enabled']['default'])
        self.assertNotIn('default', SCHEMAS['Description'])
        self.assertNotIn('default', SCHEMAS['SourcePatch']['properties']['enabled'])

    def test_paper_capability_exact_list(self):
        schema = SCHEMAS['CapabilityView']['properties']['supported_upload_formats']['properties']['paper']
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid(['pdf']))
        self.assertFalse(validator.is_valid([]))
        self.assertFalse(validator.is_valid(['pdf', 'pdf']))

    def test_request_only_does_not_claim_success_schema(self):
        op = SPEC_DATA['paths']['/projects/{project_id}/research-sessions/{session_id}/messages']['post']
        self.assertEqual(op['x-coverage'], 'request-only')
        self.assertEqual(list(op['responses']), ['default'])
        self.assertFalse(valid('ConstructionAnalysisRequest', {'expected_revision':'r1','acknowledged_risk_ids':[], 'model_selection':{}}))
        self.assertFalse(valid('ChapterIssueResolution', {'expected_revision':'r1','issue_revision':'i1','action':'ignore','replacement_markdown':'overwrite'}))

    def test_inline_schema_and_text_drift_fail(self):
        changed = copy.deepcopy(SPEC_DATA)
        changed['paths']['/me']['get']['responses']['200']['content']['application/json']['schema']['additionalProperties'] = True
        with self.assertRaises(AssertionError):
            check(changed, json.loads(COVERAGE.read_text()))
        cov = json.loads(COVERAGE.read_text())
        cov['normative_fingerprints']['04_api_contracts.md'] = 'unreviewed'
        with self.assertRaises(AssertionError):
            check(SPEC_DATA, cov)

    def test_required_headers_and_nullable_objects_fail_closed(self):
        for header in ['X-CSRF-Token', 'Idempotency-Key']:
            changed = copy.deepcopy(SPEC_DATA)
            for parameter in changed['paths']['/projects']['post']['parameters']:
                if parameter['name'] == header:
                    parameter['required'] = False
            with self.assertRaises(AssertionError):
                check(changed, json.loads(COVERAGE.read_text()))
        changed = copy.deepcopy(SPEC_DATA)
        changed['components']['schemas']['Unsafe'] = {'type':['object','null']}
        with self.assertRaises(AssertionError):
            check(changed, json.loads(COVERAGE.read_text()))

    def test_secret_set_clear_disjoint(self):
        self.assertTrue(valid('SecretWrite', {'operation': 'set', 'value': 'secret'}))
        self.assertTrue(valid('SecretWrite', {'operation': 'clear'}))
        self.assertFalse(valid('SecretWrite', {'operation': 'clear', 'value': 'secret'}))
        self.assertFalse(valid('SecretWrite', {'operation': 'set'}))
        self.assertFalse(valid('SecretView', {'configured': True, 'hint': None, 'value': 'secret'}))

    def test_formats_and_model_selection(self):
        self.assertFalse(valid('ID', 'not-an-id'))
        self.assertFalse(valid('Time', '2026-10-19'))
        self.assertFalse(valid('Time', '2026-10-19T10:00:00+08:00'))
        self.assertTrue(valid('Time', '2026-10-19T02:00:00Z'))
        self.assertFalse(valid('ModelSelection', {'source': 'fallback', 'config_id': '00000000-0000-4000-8000-000000000001', 'model_id': 'model'}))

    def test_sse_payload_terminal_and_no_business_writes(self):
        self.assertTrue(valid('DonePayload', {'execution_status': 'failed', 'result_refs': []}))
        self.assertFalse(valid('DonePayload', {'execution_status': 'waiting_user', 'result_refs': []}))
        self.assertFalse(valid('DeltaPayload', {'text': 'x', 'knowledge_version_id': 'rewrite'}))

    def test_response_required_fields(self):
        self.assertFalse(valid('ConnectionResult', {'result_type': 'connection_test', 'payload': {}}))
        self.assertTrue(valid('ConnectionResult', {'result_type': 'connection_test', 'payload': {'status': 'failed', 'checked_at': '2026-10-19T02:00:00Z', 'reason_code': 'PROVIDER_FAILED', 'models': []}}))

    def test_breaking_and_review_required_changes(self):
        mutations = [
            lambda s: s['paths'].pop('/me'),
            lambda s: s['components']['schemas']['Register']['required'].append('extra'),
            lambda s: s['components']['schemas']['ProjectView']['properties'].pop('status'),
            lambda s: s['components']['schemas']['ExecutionStatus']['enum'].append('paused'),
            lambda s: s['paths']['/me']['get'].__setitem__('security', []),
            lambda s: s['paths']['/projects']['post'].__setitem__('x-authorization', 'enabled-user'),
            lambda s: s['x-sse-payloads'].pop('done'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(SPEC_DATA)
                mutate(changed)
                self.assertTrue(compatibility(SPEC_DATA, changed))
        self.assertEqual(compatibility(SPEC_DATA, copy.deepcopy(SPEC_DATA)), [])

    def test_addition_of_independent_schema(self):
        changed = copy.deepcopy(SPEC_DATA)
        changed['components']['schemas']['NewIndependent'] = {'type': 'string'}
        self.assertEqual(compatibility(SPEC_DATA, changed), [])

    def test_coverage_and_refs_fail_closed(self):
        cov = json.loads(COVERAGE.read_text())
        cov['source_rows'].pop()
        with self.assertRaises(AssertionError):
            check(SPEC_DATA, cov)
        changed = copy.deepcopy(SPEC_DATA)
        changed['components']['schemas']['ProjectWrite']['properties']['name'] = {'$ref': '#/components/schemas/Missing'}
        with self.assertRaises(Exception):
            check(changed, json.loads(COVERAGE.read_text()))


if __name__ == '__main__':
    unittest.main()
