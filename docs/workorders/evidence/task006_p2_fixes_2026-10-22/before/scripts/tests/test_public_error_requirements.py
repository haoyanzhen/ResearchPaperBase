"""Task006 ER-01–08: independent fixtures from 04 §5/5.1 and A04 field contract.

Expected actions, details and limits are fixed here, never generated from schemas.
These are producer-contract tests, not runtime authorization/sanitization tests.
"""
import copy
import itertools
import json
import unittest

from test_api_contracts import SCHEMAS, SPEC_DATA, valid
from test_public_errors import CASES, RID, action, error
from check_api_contracts import COVERAGE, check, compatibility

ACTIONS = {
    'correct_request': '修正请求', 'reload_page': '重新读取第一页',
    'reauthenticate': '重新认证', 'refresh_csrf': '刷新请求凭据',
    'check_result': '核查原操作结果', 'refresh_confirmation': '重新查看确认依据',
    'reload_task': '重新读取状态', 'reload_resource': '重新读取',
    'repair_configuration': '检查配置', 'retry_request': '按原请求条件重试',
}
# Explicit partition of the 42 public reasons by permitted non-null advice.
ACTION_GROUPS = {
    'correct_request': 'VALIDATION_BAD_REQUEST VALIDATION_CURSOR_MISMATCH VALIDATION_PAYLOAD_TOO_LARGE VALIDATION_UNSUPPORTED_FORMAT VALIDATION_FIELD_INVALID VALIDATION_UNKNOWN_FIELD VALIDATION_FILE_UNREADABLE',
    'reload_page': 'VALIDATION_CURSOR_EXPIRED',
    'reauthenticate': 'AUTH_REQUIRED AUTH_SESSION_INVALID AUTH_ACCOUNT_DISABLED AUTH_INVALID_CREDENTIALS',
    'refresh_csrf': 'PERMISSION_CSRF_REJECTED',
    'check_result': 'STATE_IDEMPOTENCY_CONFLICT STATE_RESOURCE_LIMIT PROVIDER_FAILED PROVIDER_UNAVAILABLE PROVIDER_TIMEOUT STORAGE_INTERNAL_FAILURE',
    'refresh_confirmation': 'STATE_CONFIRMATION_STALE STATE_CONFIRMATION_REQUIRED',
    'reload_task': 'LOCK_CONSTRUCTION_OCCUPIED LOCK_RESPONSE_ACTIVE LOCK_CONTENT_BUSY STATE_EVENT_REPLAY_UNAVAILABLE',
    'reload_resource': 'VERSION_REQUIRED VERSION_BINDING_MISMATCH VERSION_BASELINE_STALE STATE_REVISION_CONFLICT STATE_REVISION_REQUIRED',
    'repair_configuration': 'CONFIG_MODEL_SELECTION_REQUIRED CONFIG_MISSING CONFIG_SECRET_UNAVAILABLE CONFIG_SOURCE_DISABLED CONFIG_CONNECTION_FAILED',
    None: 'PERMISSION_ADMIN_REQUIRED PERMISSION_RESOURCE_UNAVAILABLE STATE_OPERATION_NOT_ALLOWED STATE_PROJECT_READ_ONLY STATE_NOT_CANCELLABLE STATE_LAST_ADMIN_REQUIRED STORAGE_FILE_UNAVAILABLE',
}
EXPECTED_ACTION = {code: name for name, codes in ACTION_GROUPS.items() for code in codes.split()}
TECHNICAL = {'STATE_RESOURCE_LIMIT', 'PROVIDER_FAILED', 'PROVIDER_UNAVAILABLE', 'PROVIDER_TIMEOUT', 'STORAGE_INTERNAL_FAILURE'}
TASK_CODES = set(ACTION_GROUPS['reload_task'].split())
FIELD_CODES = {'VALIDATION_FIELD_INVALID', 'VALIDATION_UNKNOWN_FIELD', 'VALIDATION_FILE_UNREADABLE'}
DEPENDENCY_CODES = (TECHNICAL - {'STORAGE_INTERNAL_FAILURE'}) | {'CONFIG_CONNECTION_FAILED'}
DETAILS = {
    'fields': {'fields': [{'field': 'model_selection.model_id', 'reason': 'required'}]},
    'task': {'status_url': '/api/v1/tasks/' + RID},
    'revision': {'current_revision': 'r2', 'resource_url': '/api/v1/projects/' + RID},
    'dependency': {'reason': 'network'},
    'submission': {'outcome': 'not_accepted'},
}
DETAIL_CODES = {'fields': FIELD_CODES, 'task': TASK_CODES,
                'revision': {'STATE_REVISION_CONFLICT'},
                'dependency': DEPENDENCY_CODES, 'submission': TECHNICAL}


class PublicErrorRequirementTests(unittest.TestCase):
    def test_er01_er04_er06_all_actions_and_details_are_reason_specific(self):
        self.assertEqual(set(EXPECTED_ACTION), {c for c, _, _ in CASES})
        for code, _, category in CASES:
            base = error(code, category)
            for name, label in ACTIONS.items():
                with self.subTest(code=code, action=name):
                    self.assertEqual(valid('PublicError', base | {'recovery': action(name, label)}),
                                     name == EXPECTED_ACTION[code])
            for shape, details in DETAILS.items():
                with self.subTest(code=code, details=shape):
                    self.assertEqual(valid('PublicError', base | {'details': details}),
                                     code in DETAIL_CODES[shape])
            for field in ('code', 'category', 'message', 'retryable'):
                with self.subTest(code=code, null=field):
                    self.assertFalse(valid('PublicError', base | {field: None}))
            if code != 'PERMISSION_RESOURCE_UNAVAILABLE':
                for length in (1, 256):
                    self.assertTrue(valid('PublicError', base | {'message': '文' * length}))
                for length in (0, 257):
                    self.assertFalse(valid('PublicError', base | {'message': '文' * length}))

    def test_er01_er03_nested_required_types_and_whitelists(self):
        fixtures = {
            'ErrorFieldsDetails': DETAILS['fields'], 'ErrorTaskDetails': DETAILS['task'],
            'ErrorRevisionDetails': DETAILS['revision'], 'ErrorDependencyDetails': DETAILS['dependency'],
            'ErrorSubmissionDetails': DETAILS['submission'],
            'ErrorFieldIssue': {'field': 'model_id', 'reason': 'invalid'},
        }
        for schema, value in fixtures.items():
            with self.subTest(schema=schema):
                self.assertTrue(valid(schema, value))
                self.assertFalse(valid(schema, value | {'raw_response': 'SYNTHETIC_PRIVATE'}))
                for key in value:
                    missing = copy.deepcopy(value)
                    del missing[key]
                    self.assertFalse(valid(schema, missing))
                    for bad in (None, 1, True, {}, []):
                        self.assertFalse(valid(schema, value | {key: bad}), (schema, key, bad))

    def test_er01_er03_field_paths_enums_and_array_boundaries(self):
        for field in ('model_id', 'model_selection.model_id', 'items.0.name', 'a' * 128):
            for reason in ('required', 'invalid', 'unknown', 'unsupported', 'too_large', 'unreadable'):
                self.assertTrue(valid('ErrorFieldIssue', {'field': field, 'reason': reason}), field)
        for field in ('', 'a' * 129, 'api-key', 'CamelCase', 'items[0]', 'a..b', '../secret', 'a\\b', 'a\nb'):
            self.assertFalse(valid('ErrorFieldIssue', {'field': field, 'reason': 'invalid'}), field)
        self.assertFalse(valid('ErrorFieldIssue', {'field': 'model_id', 'reason': 'secret'}))
        item = {'field': 'model_id', 'reason': 'invalid'}
        for count in (1, 100):
            self.assertTrue(valid('ErrorFieldsDetails', {'fields': [item] * count}))
        for count in (0, 101):
            self.assertFalse(valid('ErrorFieldsDetails', {'fields': [item] * count}))
        for reason in ('format', 'protocol', 'authentication', 'network', 'model', 'rate_limit', 'quota', 'unavailable', 'timeout', 'failed'):
            self.assertTrue(valid('ErrorDependencyDetails', {'reason': reason}))
        self.assertFalse(valid('ErrorDependencyDetails', {'reason': 'raw diagnostic'}))
        for outcome in ('not_accepted', 'unknown'):
            self.assertTrue(valid('ErrorSubmissionDetails', {'outcome': outcome}))
        self.assertFalse(valid('ErrorSubmissionDetails', {'outcome': 'accepted'}))

    def test_er03_er04_reference_and_revision_boundaries(self):
        for url in ('/api/v1/tasks/' + RID, '/api/v1/' + 'a' * 504):
            self.assertTrue(valid('ErrorResourceURL', url))
        for url in ('/api/v1/' + 'a' * 505, '/api/v1/', 'https://evil.test/api/v1/x',
                    '//evil.test/api/v1/x', '/etc/passwd', '/api/v1/../secret',
                    '/api/v1/x?token=secret', '/api/v1/x#private', '/api/v1/%2e%2e', '/api/v1/a b'):
            self.assertFalse(valid('ErrorResourceURL', url), url)
        for revision, expected in [('', False), ('r', True), ('r' * 128, True), ('r' * 129, False)]:
            self.assertEqual(valid('ErrorRevisionDetails', DETAILS['revision'] | {'current_revision': revision}), expected)

    def test_er02_er06_recovery_labels_and_closed_objects(self):
        for code, _, category in CASES:
            name = EXPECTED_ACTION[code]
            if name is None:
                continue
            good = action(name, ACTIONS[name])
            for bad in ({'action': name}, {'label': ACTIONS[name]}, good | {'label': '执行私有操作'},
                        good | {'action': None}, good | {'label': None}, good | {'url': '/private'},
                        good | {'force': True}):
                with self.subTest(code=code, recovery=bad):
                    self.assertFalse(valid('PublicError', error(code, category) | {'recovery': bad}))
        hidden = error('PERMISSION_RESOURCE_UNAVAILABLE', 'permission')
        for details in DETAILS.values():
            self.assertFalse(valid('PublicError', hidden | {'details': details}))

    def test_er05_er07_complete_submission_retry_truth_table(self):
        for code, _, category in CASES:
            if code not in TECHNICAL:
                continue
            for outcome, retryable, advice in itertools.product(
                    (None, 'not_accepted', 'unknown'), (False, True), (None, 'check_result', 'retry_request')):
                value = error(code, category) | {
                    'details': None if outcome is None else {'outcome': outcome},
                    'retryable': retryable,
                    'recovery': None if advice is None else action(advice, ACTIONS[advice]),
                }
                expected = ((outcome == 'not_accepted' and advice == 'retry_request') if retryable
                            else (advice == 'check_result' if outcome == 'unknown' else advice != 'retry_request'))
                with self.subTest(code=code, outcome=outcome, retryable=retryable, advice=advice):
                    self.assertEqual(valid('PublicError', value), expected)
                    self.assertEqual(valid('TaskError', value), expected and not retryable)
                    self.assertEqual(valid('ErrorPayload', {'error': value}), expected and not retryable)

    def test_er01_er07_all_http_statuses_and_envelope_boundaries(self):
        statuses = {status for _, status, _ in CASES}
        for code, status, category in CASES:
            value = error(code, category)
            envelope = {'error': value, 'meta': {'request_id': RID}}
            for actual in statuses:
                with self.subTest(code=code, http=actual):
                    self.assertEqual(valid('ErrorEnvelope' + str(actual), envelope), actual == status)
            self.assertTrue(valid('TaskError', value))
            self.assertTrue(valid('ErrorPayload', {'error': value}))
            for schema in ('ErrorEnvelope', 'ErrorEnvelope' + str(status)):
                for bad in ({'error': value}, {'meta': {'request_id': RID}}, envelope | {'private': True},
                            envelope | {'meta': None}, envelope | {'meta': {'request_id': 'not-uuid'}},
                            envelope | {'meta': {'request_id': RID, 'stack': 'private'}}):
                    self.assertFalse(valid(schema, bad))
        for bad in ({}, {'error': None}, {'error': error('AUTH_REQUIRED', 'auth'), 'private': True}):
            self.assertFalse(valid('ErrorPayload', bad))

    def test_er08_error_coverage_and_response_drift_rejected(self):
        coverage = json.loads(COVERAGE.read_text())
        changed = copy.deepcopy(coverage)
        changed['public_errors']['variants'].pop()
        with self.assertRaisesRegex(AssertionError, 'public error coverage drift'):
            check(SPEC_DATA, changed)
        changed = copy.deepcopy(SPEC_DATA)
        changed['components']['responses']['PublicError503']['content']['application/json']['schema']['$ref'] = '#/components/schemas/ErrorEnvelope500'
        with self.assertRaises(AssertionError):
            check(changed, coverage)
        for section, name in [('schemas', 'TaskError'), ('schemas', 'ErrorProviderTimeout'),
                              ('responses', 'PublicError429')]:
            changed = copy.deepcopy(SPEC_DATA)
            del changed['components'][section][name]
            self.assertTrue(compatibility(SPEC_DATA, changed), (section, name))
