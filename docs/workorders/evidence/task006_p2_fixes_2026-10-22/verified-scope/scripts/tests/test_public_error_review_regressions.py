"""Task006 independent review R01–R03 requirement regressions."""
import copy
import json
import unittest
from test_api_contracts import SPEC_DATA, valid
from test_public_errors import RID, error, action
from check_api_contracts import COVERAGE, check


class ReviewRegressionTests(unittest.TestCase):
    def test_r01_replay_requires_task_status_reference(self):
        base = error('STATE_EVENT_REPLAY_UNAVAILABLE', 'state')
        for recovery in (None, action('reload_task', '重新读取状态')):
            for details in (None, {}, {'status_url': None}):
                self.assertFalse(valid('PublicError', base | {'details': details, 'recovery': recovery}))
            good = base | {'details': {'status_url': '/api/v1/tasks/' + RID}, 'recovery': recovery}
            for schema in ('PublicError', 'TaskError'):
                self.assertTrue(valid(schema, good))
            self.assertTrue(valid('ErrorEnvelope409', {'error': good, 'meta': {'request_id': RID}}))
            self.assertTrue(valid('ErrorPayload', {'error': good}))

    def test_r01_task_status_url_exact_route(self):
        for task_id in (RID, RID.upper(), 'ffffffff-ffff-ffff-ffff-ffffffffffff'):
            self.assertTrue(valid('ErrorTaskDetails', {'status_url': '/api/v1/tasks/' + task_id}))
        for url in ('/api/v1/me', '/api/v1/tasks/not-uuid', '/api/v1/tasks/',
                    '/api/v1/tasks/' + RID + '/events', '/api/v1/tasks/' + RID + '/',
                    '/api/v1/tasks/' + RID + '?token=x', '/api/v1/tasks/' + RID + '#x',
                    '/api/v1/tasks/' + RID + '\n', 'https://evil.test/api/v1/tasks/' + RID,
                    '/api/v1/tasks/../' + RID):
            self.assertFalse(valid('ErrorTaskDetails', {'status_url': url}), url)
        # Lock errors can still omit an undisclosable task reference.
        self.assertTrue(valid('PublicError', error('LOCK_CONTENT_BUSY', 'lock_conflict')))

    def test_r02_accepted_carriers_reject_not_accepted(self):
        for code, category in [('STATE_RESOURCE_LIMIT', 'state'), ('STORAGE_INTERNAL_FAILURE', 'storage'),
                               ('PROVIDER_FAILED', 'provider'), ('PROVIDER_UNAVAILABLE', 'provider'),
                               ('PROVIDER_TIMEOUT', 'provider')]:
            for advice in (None, action('check_result', '核查原操作结果')):
                value = error(code, category) | {'details': {'outcome': 'not_accepted'}, 'recovery': advice}
                self.assertTrue(valid('PublicError', value))
                self.assertFalse(valid('TaskError', value))
                self.assertFalse(valid('ErrorPayload', {'error': value}))
            unknown = error(code, category) | {'details': {'outcome': 'unknown'},
                                              'recovery': action('check_result', '核查原操作结果')}
            self.assertTrue(valid('TaskError', unknown))
            self.assertTrue(valid('ErrorPayload', {'error': unknown}))
            self.assertTrue(valid('TaskError', error(code, category)))

    def test_r03_status_and_envelope_membership_drift_rejected(self):
        coverage = json.loads(COVERAGE.read_text())
        check(SPEC_DATA, coverage)  # An unrelated broken baseline must not make mutations pass.
        def metadata(s):
            s['components']['schemas']['ErrorPermissionResourceUnavailable']['x-http-status'] = 500
        def removed(s):
            s['components']['schemas']['ErrorEnvelope409']['properties']['error']['oneOf'].pop()
        def added(s):
            s['components']['schemas']['ErrorEnvelope500']['properties']['error']['oneOf'].append(
                {'$ref': '#/components/schemas/ErrorPermissionResourceUnavailable'})
        def duplicate(s):
            members = s['components']['schemas']['ErrorEnvelope404']['properties']['error']['oneOf']
            members.append(copy.deepcopy(members[0]))
        for mutate, expected_message in ((metadata, 'public error status groups drift'),
                                         (removed, 'public error status membership drift'),
                                         (added, 'public error status membership drift'),
                                         (duplicate, 'public error status membership drift')):
            changed = copy.deepcopy(SPEC_DATA)
            mutate(changed)
            with self.subTest(mutation=mutate.__name__), self.assertRaisesRegex(
                    AssertionError, expected_message):
                check(changed, coverage)
