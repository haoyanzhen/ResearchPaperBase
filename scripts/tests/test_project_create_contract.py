"""B01 Project.Create wire contract; requirements from 04/04-01, not runtime tests."""
import copy
import json
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from test_api_contracts import SPEC_DATA, SCHEMAS, COVERAGE, check, compatibility, valid
from test_public_errors import error, CASES, RID

EXPECTED = {
    '400': ['VALIDATION_BAD_REQUEST'],
    '401': ['AUTH_REQUIRED', 'AUTH_SESSION_INVALID', 'AUTH_ACCOUNT_DISABLED'],
    '403': ['PERMISSION_CSRF_REJECTED'],
    '404': ['PERMISSION_RESOURCE_UNAVAILABLE'],
    '409': ['STATE_IDEMPOTENCY_CONFLICT'],
    '413': ['VALIDATION_PAYLOAD_TOO_LARGE'],
    '415': ['VALIDATION_UNSUPPORTED_FORMAT'],
    '422': ['VALIDATION_FIELD_INVALID', 'VALIDATION_UNKNOWN_FIELD'],
    '429': ['STATE_RESOURCE_LIMIT'],
    '500': ['STORAGE_INTERNAL_FAILURE'],
}
TIME = '2026-10-24T00:00:00Z'
PROJECT = {'id': RID, 'revision': 'r1', 'created_at': TIME, 'updated_at': TIME,
           'name': 'Study', 'description': '', 'research_scope': '', 'status': 'active',
           'default_knowledge_version_id': None, 'last_construction_at': None,
           'last_activity_at': None, 'permissions': {'access': True, 'use': True, 'delete': True},
           'available_actions': []}


def operation(spec=SPEC_DATA):
    return spec['paths']['/projects']['post']


def accepts(schema, value):
    return Draft202012Validator(schema | {'components': {'schemas': SCHEMAS}},
                                format_checker=FormatChecker()).is_valid(value)


class ProjectCreateContractTests(unittest.TestCase):
    def test_pc01_request_boundaries_and_no_owner_status_revision(self):
        for name in ['A', '中' * 200]:
            self.assertTrue(valid('ProjectWrite', {'name': name}))
        for name in ['', ' ', '\n\t', 'x' * 201, None, 1]:
            self.assertFalse(valid('ProjectWrite', {'name': name}))
        self.assertFalse(valid('ProjectWrite', {}))
        for field in ['owner_id', 'status', 'expected_revision', 'force', 'confirmation_token']:
            self.assertFalse(valid('ProjectWrite', {'name': 'Study', field: 'forged'}))
        for field in ['description', 'research_scope']:
            self.assertTrue(valid('ProjectWrite', {'name': 'Study', field: 'x' * 10000}))
            for value in [None, 1, 'x' * 10001]:
                self.assertFalse(valid('ProjectWrite', {'name': 'Study', field: value}))

    def test_pc02_headers_and_creation_transport(self):
        op = operation()
        self.assertEqual(op['security'], [{'sessionCookie': []}])
        params = {p['name']: p for p in op['parameters']}
        self.assertEqual(set(params), {'X-CSRF-Token', 'Idempotency-Key'})
        for p in params.values():
            self.assertTrue(p['required']); self.assertEqual(p['in'], 'header')
        schema = params['Idempotency-Key']['schema']
        for v in ['a' * 16, 'z' * 128, RID]:
            self.assertTrue(accepts(schema, v))
        for v in ['', 'a' * 15, 'z' * 129, '中' * 16, 'a' * 15 + '\n']:
            self.assertFalse(accepts(schema, v))
        self.assertTrue(op['requestBody']['required'])
        self.assertEqual(set(op['requestBody']['content']), {'application/json'})
        self.assertEqual(op['requestBody']['content']['application/json']['schema'],
                         {'$ref': '#/components/schemas/ProjectWrite'})
        self.assertTrue(op['responses']['201']['headers']['Location']['required'])

    def test_pc03_success_meta_requires_real_expiry_and_closed_envelope(self):
        schema = operation()['responses']['201']['content']['application/json']['schema']
        good = {'data': PROJECT, 'meta': {'request_id': RID, 'idempotency_expires_at': TIME}}
        self.assertTrue(accepts(schema, good))
        self.assertTrue(accepts(schema, good | {'meta': good['meta'] | {'original_request_id': RID}}))
        for value in [None, 'tomorrow', '2026-10-24T00:00:00+08:00']:
            self.assertFalse(accepts(schema, good | {'meta': good['meta'] | {'idempotency_expires_at': value}}))
        for branch, keys in [('meta', ['request_id', 'idempotency_expires_at']),
                             ('data', ['id', 'revision', 'status', 'permissions'])]:
            for key in keys:
                bad = copy.deepcopy(good); del bad[branch][key]
                self.assertFalse(accepts(schema, bad))
            bad = copy.deepcopy(good); bad[branch]['unknown'] = True
            self.assertFalse(accepts(schema, bad))
        for field in ['data', 'meta']:
            bad = copy.deepcopy(good); del bad[field]; self.assertFalse(accepts(schema, bad))
        self.assertFalse(accepts(schema, good | {'task': RID}))
        # Generic async metadata remains nullable; this operation-specific narrowing is local.
        self.assertTrue(valid('IdempotentMeta', {'request_id': RID, 'idempotency_expires_at': None}))

    def test_pc04_exact_errors_and_all_unrelated_variants_rejected(self):
        op = operation()
        self.assertEqual(op['x-error-codes'], EXPECTED)
        self.assertEqual(set(op['responses']), {'201'} | set(EXPECTED))
        for status in EXPECTED:
            schema = op['responses'][status]['content']['application/json']['schema']
            for code, actual_status, category in CASES:
                with self.subTest(status=status, code=code):
                    value = {'error': error(code, category), 'meta': {'request_id': RID}}
                    self.assertEqual(accepts(schema, value), code in EXPECTED[status])

    def test_pc05_safe_failure_projection_and_unknown_outcome(self):
        op = operation()
        for status, code, cat in [('500', 'STORAGE_INTERNAL_FAILURE', 'storage'),
                                  ('429', 'STATE_RESOURCE_LIMIT', 'state')]:
            schema = op['responses'][status]['content']['application/json']['schema']
            value = {'error': error(code, cat) | {'details': {'outcome': 'unknown'},
                     'recovery': {'action': 'check_result', 'label': '核查原操作结果'}},
                     'meta': {'request_id': RID}}
            self.assertTrue(accepts(schema, value))
            bad = copy.deepcopy(value); bad['error']['retryable'] = True
            self.assertFalse(accepts(schema, bad))
            bad = copy.deepcopy(value); bad['error']['details']['sql'] = 'private'
            self.assertFalse(accepts(schema, bad))

    def test_pc06_no_store_and_retry_after(self):
        for status, response in operation()['responses'].items():
            header = response['headers']['Cache-Control']
            self.assertTrue(header['required'])
            self.assertEqual(header['schema'], {'type': 'string', 'const': 'no-store'})
        retry = operation()['responses']['429']['headers']['Retry-After']
        self.assertTrue(retry['required'])
        self.assertTrue(accepts(retry['schema'], 0)); self.assertFalse(accepts(retry['schema'], -1))

    def test_pc07_drift_guard_rejects_missing_or_widened_bindings(self):
        for mutation in ['response', 'subset', 'cache', 'location', 'coverage', 'expiry']:
            s = copy.deepcopy(SPEC_DATA); c = json.loads(COVERAGE.read_text()); op = operation(s)
            if mutation == 'response': del op['responses']['401']
            elif mutation == 'subset': op['responses']['409']['content']['application/json']['schema'] = {'$ref': '#/components/schemas/ErrorEnvelope409'}
            elif mutation == 'cache': del op['responses']['201']['headers']['Cache-Control']
            elif mutation == 'location': op['responses']['201']['headers']['Location']['required'] = False
            elif mutation == 'coverage': c['operation_coverage']['Project.Create']['status'] = 'request-success-partial'
            else: op['responses']['201']['content']['application/json']['schema']['properties']['meta'] = {'$ref': '#/components/schemas/IdempotentMeta'}
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                check(s, c)

    def test_pc08_existing_operation_change_still_requires_review(self):
        old = copy.deepcopy(SPEC_DATA)
        old['paths']['/projects']['post']['responses']['201']['description'] = 'previous'
        self.assertIn('operation changed/removed: POST /projects', compatibility(old, SPEC_DATA))
