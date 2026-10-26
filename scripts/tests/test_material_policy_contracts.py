"""A05 N-T01–08 producer contracts; no runtime permission/concurrency claim.

Fixtures/expected routes and error reasons come from 08-01 and 04-01 §10.
"""
import copy
import json
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from test_api_contracts import SPEC_DATA, SCHEMAS, valid
from test_public_errors import error
from check_api_contracts import COVERAGE, check, compatibility

ID = '00000000-0000-4000-8000-000000000001'
TIME = '2026-10-22T01:00:00Z'
BASE = '/projects/{project_id}'
ROUTES = [
    ('get', BASE + '/material-policy', 'MaterialPolicy.Read', None, 'MaterialPolicyView'),
    ('put', BASE + '/material-policy', 'MaterialPolicy.Update', 'MaterialPolicyWrite', 'MaterialPolicyView'),
    ('get', BASE + '/material-sources/{source_id}/classification', 'MaterialSource.ReadClassification', None, 'MaterialClassificationView'),
    ('post', BASE + '/material-sources/{source_id}/classification/confirm', 'MaterialSource.ConfirmClassification', 'MaterialClassificationWrite', 'MaterialClassificationConfirmedView'),
    ('post', BASE + '/material-sources/{source_id}/classification/correct', 'MaterialSource.CorrectClassification', 'MaterialClassificationWrite', 'MaterialClassificationConfirmedView'),
]
POLICY = {'user_id': ID, 'project_id': ID, 'mode': 'public_only', 'revision': 'p1', 'risk_acknowledged_at': None}
WRITE = {'expected_revision': 'c1', 'content_revision': 'text1', 'classification': 'private', 'basis': 'Owner verified this uploaded source.', 'explicit_confirmation': True}
PROVENANCE = {'kind': 'uploaded_file', 'submission_scope_id': None, 'dependency_status': 'complete'}
VIEW = {'source': {'project_id': ID, 'source_id': ID, 'content_revision': 'text1'}, 'classification': 'private', 'confirmation_status': 'unconfirmed', 'revision': 'c1', 'confirmation': None, 'provenance': PROVENANCE}
FACT = {'basis': 'Owner verified specific content.', 'confirmed_by': ID, 'confirmed_at': TIME}
FIXTURES = {'MaterialPolicyWrite': {'expected_revision': 'p1', 'mode': 'public_only', 'risk_acknowledged': False}, 'MaterialPolicyView': POLICY, 'MaterialSourceIdentity': VIEW['source'], 'MaterialProvenance': PROVENANCE, 'MaterialClassificationWrite': WRITE, 'MaterialClassificationView': VIEW, 'MaterialClassificationFact': FACT, 'MaterialUseNotice': {'reason': 'required_history_restricted', 'message': 'Required history is restricted.'}}


def accepts(schema, value):
    return Draft202012Validator(schema | {'components': {'schemas': SCHEMAS}}, format_checker=FormatChecker()).is_valid(value)


class MaterialPolicyContractTests(unittest.TestCase):
    def test_nt01_scope_and_risk_combinations(self):
        for mode, ack, expected in [('public_only', False, True), ('public_only', True, False), ('allow_private', True, True), ('allow_private', False, False), ('all', True, False)]:
            self.assertEqual(valid('MaterialPolicyWrite', {'expected_revision': 'p1', 'mode': mode, 'risk_acknowledged': ack}), expected)
        self.assertTrue(valid('MaterialPolicyView', POLICY))
        self.assertFalse(valid('MaterialPolicyView', POLICY | {'mode': 'allow_private'}))
        self.assertTrue(valid('MaterialPolicyView', POLICY | {'mode': 'allow_private', 'risk_acknowledged_at': TIME}))
        for field in ('user_id', 'project_id', 'provider', 'allow', 'confirmation_token'):
            self.assertFalse(valid('MaterialPolicyWrite', FIXTURES['MaterialPolicyWrite'] | {field: ID}))

    def test_nt02_classification_confirmation_is_independent(self):
        for classification in ('private', 'public'):
            for status, fact, expected in [('unconfirmed', None, True), ('unconfirmed', FACT, False), ('confirmed', None, False), ('confirmed', FACT, True)]:
                self.assertEqual(valid('MaterialClassificationView', VIEW | {'classification': classification, 'confirmation_status': status, 'confirmation': fact}), expected)
        for value in ('unknown', 'open_source', None):
            self.assertFalse(valid('MaterialClassificationView', VIEW | {'classification': value}))
        for classification in ('private', 'public'):
            self.assertTrue(valid('MaterialClassificationWrite', WRITE | {'classification': classification}))
        self.assertFalse(valid('MaterialClassificationWrite', WRITE | {'explicit_confirmation': False}))

    def test_nt03_identity_basis_and_no_metadata_bypass(self):
        for value in ('', ' ', 'a' * 2001, None, 1):
            self.assertFalse(valid('MaterialClassificationWrite', WRITE | {'basis': value}))
        for length in (1, 2000):
            self.assertTrue(valid('MaterialClassificationWrite', WRITE | {'basis': '证' * length}))
        for field in ('doi', 'content_hash', 'project_id', 'source_id', 'confirmed_by', 'confirmed_at', 'provenance', 'force', 'content', 'knowledge_version_id'):
            self.assertFalse(valid('MaterialClassificationWrite', WRITE | {field: ID}), field)
        for field in ('classification', 'mode', 'risk_acknowledged', 'provenance'):
            self.assertFalse(valid('ProjectPatch', {'expected_revision': 'r1', field: 'public'}))
            self.assertNotIn(field, SCHEMAS['WorkspaceContextWrite']['properties'])

    def test_nt04_nt07_each_operation_permissions_headers_and_sync(self):
        for method, path, name, req, res in ROUTES:
            op = SPEC_DATA['paths'][path][method]
            with self.subTest(operation=name):
                self.assertEqual(op['operationId'], name)
                self.assertEqual(op['security'], [{'sessionCookie': []}])
                self.assertEqual(op['x-authorization'], 'project-owner-readable' if method == 'get' else 'project-owner-active')
                self.assertEqual(op['x-phase'], 'P0')
                self.assertEqual(op['x-version-binding'], 'not-applicable')
                self.assertEqual(op['x-errors'], '#/components/schemas/PublicError')
                params = {p['name']: p for p in op['parameters']}
                self.assertTrue(params['project_id']['required'])
                if 'source_id' in path:
                    self.assertTrue(params['source_id']['required'])
                self.assertEqual('X-CSRF-Token' in params, method != 'get')
                self.assertEqual('Idempotency-Key' in params, method == 'post')
                if req:
                    self.assertTrue(op['requestBody']['required'])
                    self.assertEqual(op['requestBody']['content']['application/json']['schema']['$ref'], '#/components/schemas/' + req)
                else:
                    self.assertNotIn('requestBody', op)
                success = op['responses']['200']['content']['application/json']['schema']
                self.assertEqual(success['properties']['data']['$ref'], '#/components/schemas/' + res)
                fixture = POLICY if res == 'MaterialPolicyView' else VIEW
                meta = {'request_id': ID}
                if method == 'post':
                    fixture = VIEW | {'confirmation_status': 'confirmed', 'confirmation': FACT}
                    meta['idempotency_expires_at'] = '2026-10-24T01:00:00Z'
                self.assertTrue(accepts(success, {'data': fixture, 'meta': meta}))
                self.assertFalse(accepts(success, {'data': fixture}))
                self.assertFalse(accepts(success, {'data': fixture | {'task': {}}, 'meta': meta}))
                self.assertNotIn('202', op['responses'])

    def test_nt05_nonreusable_revisions_and_frozen_scope_contract(self):
        for name in ('MaterialPolicyWrite', 'MaterialClassificationWrite'):
            for value in ('', None, 1, 'r' * 129):
                self.assertFalse(valid(name, FIXTURES[name] | {'expected_revision': value}))
            for value in ('r', 'r' * 128):
                self.assertTrue(valid(name, FIXTURES[name] | {'expected_revision': value}))
        for value in ('', None, 1, 'r' * 129):
            self.assertFalse(valid('MaterialClassificationWrite', WRITE | {'content_revision': value}))
        for method, path, *_ in ROUTES:
            semantic = SPEC_DATA['paths'][path][method]['x-material-policy']
            self.assertEqual(semantic['revision'], 'non-reusable')
            self.assertEqual(semantic['current_policy_at'], ['read', 'dispatch', 'commit'])
            self.assertEqual(semantic['preserves'], ['knowledge_version', 'frozen_inputs', 'confirmation_scope', 'historical_content'])
            self.assertIs(semantic['task_created'], False)
            self.assertIs(semantic['synchronous'], True)

    def test_nt06_provenance_and_restricted_notice_variants(self):
        for kind in ('current_submission', 'historical_input', 'uploaded_file', 'retrieved_content', 'derived_content', 'unknown'):
            for scope in (None, ID):
                for status in ('complete', 'incomplete', 'unknown'):
                    expected = ((scope is not None and status == 'complete') if kind == 'current_submission' else (scope is None and (kind != 'unknown' or status == 'unknown')))
                    self.assertEqual(valid('MaterialProvenance', {'kind': kind, 'submission_scope_id': scope, 'dependency_status': status}), expected)
        for reason in ('private_source', 'classification_unconfirmed', 'provenance_unknown', 'dependencies_incomplete', 'required_history_restricted', 'available_subset'):
            self.assertTrue(valid('MaterialUseNotice', {'reason': reason, 'message': '范围受限'}))
        for reason in ('public_by_default', 'silently_drop_history', 'rerun'):
            self.assertFalse(valid('MaterialUseNotice', {'reason': reason, 'message': 'invalid'}))
        self.assertFalse(valid('MaterialProvenance', PROVENANCE | {'allow': True}))

    def test_nt07_exact_error_reasons_and_status_envelopes(self):
        by_code = {v['properties']['code']['const']: v for v in SCHEMAS.values() if 'x-http-status' in v}
        common = {400: ['VALIDATION_BAD_REQUEST'], 401: ['AUTH_REQUIRED', 'AUTH_SESSION_INVALID', 'AUTH_ACCOUNT_DISABLED'], 404: ['PERMISSION_RESOURCE_UNAVAILABLE'], 422: ['VALIDATION_FIELD_INVALID', 'VALIDATION_UNKNOWN_FIELD'], 429: ['STATE_RESOURCE_LIMIT'], 500: ['STORAGE_INTERNAL_FAILURE']}
        for method, path, name, *_ in ROUTES:
            expected = copy.deepcopy(common)
            if method != 'get':
                expected.update({403: ['PERMISSION_CSRF_REJECTED'], 409: ['STATE_PROJECT_READ_ONLY', 'STATE_OPERATION_NOT_ALLOWED'], 412: ['STATE_REVISION_CONFLICT'], 428: ['STATE_REVISION_REQUIRED'], 413: ['VALIDATION_PAYLOAD_TOO_LARGE'], 415: ['VALIDATION_UNSUPPORTED_FORMAT']})
                if method == 'post':
                    expected[409].append('STATE_IDEMPOTENCY_CONFLICT')
            op = SPEC_DATA['paths'][path][method]
            self.assertEqual(op['x-error-codes'], {str(k): v for k, v in expected.items()})
            self.assertEqual(set(op['responses']), {'200'} | {str(k) for k in expected})
            for status, codes in expected.items():
                schema = op['responses'][str(status)]['content']['application/json']['schema']
                for code, variant in by_code.items():
                    value = error(code, variant['properties']['category']['const'])
                    self.assertEqual(accepts(schema, {'error': value, 'meta': {'request_id': ID}}), code in codes, (name, status, code))
            self.assertIn('Retry-After', op['responses']['429']['headers'])
        restricted = error('STATE_OPERATION_NOT_ALLOWED', 'state')
        self.assertTrue(valid('TaskError', restricted))
        self.assertFalse(valid('TaskError', restricted | {'retryable': True}))
        self.assertFalse(valid('TaskError', restricted | {'details': {'source_id': ID}}))

    def test_nt08_every_field_missing_null_type_and_unknown(self):
        for schema, fixture in FIXTURES.items():
            with self.subTest(schema=schema):
                self.assertTrue(valid(schema, fixture))
                self.assertFalse(valid(schema, fixture | {'unauthorized': True}))
                for key, value in fixture.items():
                    missing = dict(fixture)
                    del missing[key]
                    self.assertFalse(valid(schema, missing), (schema, key))
                    # Null allowed only at the explicit nullable readonly positions.
                    if value is not None:
                        self.assertFalse(valid(schema, fixture | {key: None}), (schema, key))
                    for wrong in ([], 123):
                        self.assertFalse(valid(schema, fixture | {key: wrong}), (schema, key, wrong))

    def test_nt08_identifiers_times_enums_and_text_boundaries(self):
        for key in ('user_id', 'project_id'):
            self.assertFalse(valid('MaterialPolicyView', POLICY | {key: 'not-uuid'}))
        for key in ('project_id', 'source_id'):
            self.assertFalse(valid('MaterialSourceIdentity', VIEW['source'] | {key: 'not-uuid'}))
        for value in ('', '2026-10-22', '2026-10-22T09:00:00+08:00'):
            self.assertFalse(valid('MaterialClassificationFact', FACT | {'confirmed_at': value}))
            self.assertFalse(valid('MaterialPolicyView', POLICY | {'risk_acknowledged_at': value}))
        for key in ('kind', 'dependency_status'):
            self.assertFalse(valid('MaterialProvenance', PROVENANCE | {key: 'invented'}))
        for key in ('mode',):
            self.assertFalse(valid('MaterialPolicyView', POLICY | {key: 'invented'}))
        self.assertFalse(valid('MaterialClassificationView', VIEW | {'confirmation_status': 'invented'}))
        for value in ('', ' ', 'a' * 257):
            self.assertFalse(valid('MaterialUseNotice', FIXTURES['MaterialUseNotice'] | {'message': value}))
        self.assertTrue(valid('MaterialUseNotice', FIXTURES['MaterialUseNotice'] | {'message': 'a' * 256}))

    def test_nt08_error_binding_drift_rejected(self):
        coverage = json.loads(COVERAGE.read_text())
        changed = copy.deepcopy(SPEC_DATA)
        op = changed['paths'][BASE + '/material-policy']['put']
        op['responses']['412']['content']['application/json']['schema']['allOf'][0]['$ref'] = '#/components/schemas/ErrorEnvelope428'
        with self.assertRaisesRegex(AssertionError, 'material error binding drift'):
            check(changed, coverage)
        changed = copy.deepcopy(coverage)
        changed['material_policy']['operations'].remove('MaterialPolicy.Update')
        with self.assertRaisesRegex(AssertionError, 'material coverage drift'):
            check(SPEC_DATA, changed)

    def test_nt08_coverage_and_compatibility_reject_deletion(self):
        coverage = json.loads(COVERAGE.read_text())
        for method, path, name, *_ in ROUTES:
            self.assertIn(name, coverage['typed_operations'])
            changed = copy.deepcopy(SPEC_DATA)
            del changed['paths'][path][method]
            with self.assertRaises(AssertionError):
                check(changed, coverage)
            self.assertTrue(compatibility(SPEC_DATA, changed))
        changed = copy.deepcopy(SPEC_DATA)
        changed['components']['schemas']['MaterialClassificationWrite']['additionalProperties'] = True
        with self.assertRaises(AssertionError):
            check(changed, coverage)
        self.assertTrue(compatibility(SPEC_DATA, changed))
