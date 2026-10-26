"""Independent task007 N-T01–08 wire-contract coverage, derived from 04 §4/7
and 04-01 §10 / 08-01; does not simulate persistence or permission enforcement.
"""
import copy
import unittest

from test_api_contracts import SPEC_DATA
from test_material_policy_contracts import (
    BASE, FACT, ID, POLICY, TIME, VIEW, WRITE, accepts,
)

CLASSIFICATION = BASE + '/material-sources/{source_id}/classification'
# Deliberately enumerate the approved operations, not the implementation inventory.
ENDPOINTS = [('get', BASE + '/material-policy'), ('put', BASE + '/material-policy'),
             ('get', CLASSIFICATION), ('post', CLASSIFICATION + '/confirm'),
             ('post', CLASSIFICATION + '/correct')]
CONFIRMED = VIEW | {'confirmation_status': 'confirmed', 'confirmation': FACT}
META = {'request_id': ID, 'idempotency_expires_at': '2026-10-24T01:00:00Z'}


def operation(method, path):
    return SPEC_DATA['paths'][path][method]


def success(method, path):
    return operation(method, path)['responses']['200']['content']['application/json']['schema']


def envelope(method, path):
    data = POLICY if path.endswith('/material-policy') else (CONFIRMED if method == 'post' else VIEW)
    return copy.deepcopy({'data': data, 'meta': META if method == 'post' else {'request_id': ID}})


def at(value, path):
    for key in path:
        value = value[key]
    return value


class MaterialPolicyCoverageTests(unittest.TestCase):
    def test_nt01_policy_read_and_update_preserve_prior_risk_audit(self):
        # Turning off retains the last acknowledgement; only initial default is null.
        for method in ('get', 'put'):
            schema = success(method, BASE + '/material-policy')
            for mode, timestamp, expected in (
                ('public_only', None, True), ('public_only', TIME, True),
                ('allow_private', TIME, True), ('allow_private', None, False),
            ):
                with self.subTest(method=method, mode=mode, timestamp=timestamp):
                    value = {'data': POLICY | {'mode': mode, 'risk_acknowledged_at': timestamp},
                             'meta': {'request_id': ID}}
                    self.assertEqual(accepts(schema, value), expected)

    def test_nt03_nt08_each_write_validates_actual_request_binding(self):
        for method, path in ENDPOINTS:
            if method == 'get':
                continue
            schema = operation(method, path)['requestBody']['content']['application/json']['schema']
            fixtures = ([{'expected_revision': 'p1', 'mode': mode, 'risk_acknowledged': ack}
                         for mode, ack in [('public_only', False), ('allow_private', True)]]
                        if method == 'put' else [WRITE | {'classification': c} for c in ('public', 'private')])
            for good in fixtures:
                self.assertTrue(accepts(schema, good))
                for key in good:
                    missing = dict(good)
                    del missing[key]
                    with self.subTest(method=method, path=path, missing=key):
                        self.assertFalse(accepts(schema, missing))
                    for wrong in (None, [], {}, 123, 'true' if isinstance(good[key], bool) else False):
                        with self.subTest(path=path, field=key, wrong=wrong):
                            self.assertFalse(accepts(schema, good | {key: wrong}))
                for field in ('user_id', 'project_id', 'source_id', 'confirmed_by', 'confirmed_at',
                              'provenance', 'submission_scope_id', 'provider', 'force', 'content',
                              'knowledge_version_id', 'confirmation_token'):
                    self.assertFalse(accepts(schema, good | {field: ID}), (path, field))

    def test_nt04_nt08_parameters_are_required_in_correct_locations(self):
        for method, path in ENDPOINTS:
            op = operation(method, path)
            expected = {'project_id': 'path'}
            if 'source_id' in path:
                expected['source_id'] = 'path'
            if method != 'get':
                expected['X-CSRF-Token'] = 'header'
            if method == 'post':
                expected['Idempotency-Key'] = 'header'
            self.assertEqual(len(op['parameters']), len(expected))
            self.assertEqual({p['name']: p['in'] for p in op['parameters']}, expected)
            for parameter in op['parameters']:
                self.assertIs(parameter['required'], True)
                schema = parameter['schema']
                if parameter['in'] == 'path':
                    self.assertTrue(accepts(schema, ID))
                    for wrong in ('doi:10.1/example', '', None, {}, 1):
                        self.assertFalse(accepts(schema, wrong))
                if parameter['name'] == 'Idempotency-Key':
                    for length in (16, 128):
                        self.assertTrue(accepts(schema, 'k' * length))
                    for wrong in ('k' * 15, 'k' * 129, '中' * 16, '\t' * 16, None, 1):
                        self.assertFalse(accepts(schema, wrong))
            self.assertEqual(op['x-material-policy']['scope'],
                             'authenticated-user-project' if path.endswith('/material-policy')
                             else 'project-source-content-revision')

    def test_nt07_private_responses_never_advertise_shared_caching(self):
        for method, path in ENDPOINTS:
            for status, response in operation(method, path)['responses'].items():
                with self.subTest(path=path, method=method, status=status):
                    self.assertIn('Cache-Control', response.get('headers', {}))
                    schema = response['headers']['Cache-Control']['schema']
                    self.assertTrue(accepts(schema, 'no-store'))
                    for wrong in ('public', 'private', 'max-age=60', None):
                        self.assertFalse(accepts(schema, wrong))

    def test_nt08_success_envelopes_and_nested_required_fields(self):
        for method, path in ENDPOINTS:
            schema, good = success(method, path), envelope(method, path)
            branches = [(), ('data',), ('meta',)]
            if 'source_id' in path:
                branches += [('data', 'source'), ('data', 'provenance')]
                # Exercise both confirmed GET and confirmed mutation responses.
                good['data'] = copy.deepcopy(CONFIRMED)
                branches += [('data', 'confirmation')]
            self.assertTrue(accepts(schema, good))
            for branch in branches:
                node = at(good, branch)
                for key in node:
                    for wrong in ('missing', None, [], 7):
                        bad = copy.deepcopy(good)
                        target = at(bad, branch)
                        if wrong == 'missing':
                            del target[key]
                        else:
                            target[key] = wrong
                        # The risk audit timestamp is nullable on public_only.
                        if key in ('risk_acknowledged_at', 'submission_scope_id') and wrong is None:
                            continue
                        with self.subTest(path=path, branch=branch, key=key, wrong=wrong):
                            self.assertFalse(accepts(schema, bad))
                bad = copy.deepcopy(good)
                at(bad, branch)['unauthorized'] = True
                self.assertFalse(accepts(schema, bad), (path, branch))

    def test_nt05_nt08_readonly_revisions_identities_and_fact_boundaries(self):
        for method, path in ENDPOINTS:
            schema, good = success(method, path), envelope(method, path)
            fields = [(('data',), 'revision', 'revision')]
            if 'source_id' in path:
                good['data'] = copy.deepcopy(CONFIRMED)
                fields += [(('data', 'source'), 'content_revision', 'revision'),
                           (('data', 'confirmation'), 'basis', 'basis'),
                           (('data', 'confirmation'), 'confirmed_by', 'id'),
                           (('data', 'confirmation'), 'confirmed_at', 'time')]
            invalid = {'revision': ['', 'r' * 129], 'basis': ['', ' \t\n', '证' * 2001],
                       'id': ['', 'not-uuid'], 'time': ['2026-02-30T00:00:00Z', '2026-10-23']}
            valid = {'revision': ['r', 'r' * 128], 'basis': ['证', '证' * 2000],
                     'id': [ID], 'time': [TIME]}
            for branch, key, kind in fields:
                for expected, values in [(False, invalid[kind]), (True, valid[kind])]:
                    for value in values:
                        changed = copy.deepcopy(good)
                        at(changed, branch)[key] = value
                        with self.subTest(path=path, field=key, length=len(value)):
                            self.assertEqual(accepts(schema, changed), expected)

    def test_nt06_provenance_variants_remain_bound_in_each_source_response(self):
        for method, path in ENDPOINTS[2:]:
            schema, good = success(method, path), envelope(method, path)
            for kind in ('current_submission', 'historical_input', 'uploaded_file',
                         'retrieved_content', 'derived_content', 'unknown'):
                for scope in (None, ID, 'forged'):
                    for dependency in ('complete', 'incomplete', 'unknown'):
                        expected = ((scope == ID and dependency == 'complete') if kind == 'current_submission'
                                    else scope is None and (kind != 'unknown' or dependency == 'unknown'))
                        changed = copy.deepcopy(good)
                        changed['data']['provenance'] = {'kind': kind, 'submission_scope_id': scope,
                                                        'dependency_status': dependency}
                        with self.subTest(path=path, kind=kind, scope=scope, dependency=dependency):
                            self.assertEqual(accepts(schema, changed), expected)

    def test_nt04_nt07_errors_cannot_carry_success_or_source_diagnostics(self):
        from test_public_errors import error
        for method, path in ENDPOINTS:
            for status, code, category in [('404', 'PERMISSION_RESOURCE_UNAVAILABLE', 'permission'),
                                           ('500', 'STORAGE_INTERNAL_FAILURE', 'storage')]:
                schema = operation(method, path)['responses'][status]['content']['application/json']['schema']
                good = {'error': error(code, category), 'meta': {'request_id': ID}}
                self.assertTrue(accepts(schema, good))
                self.assertFalse(accepts(schema, envelope(method, path)))
                self.assertFalse(accepts(success(method, path), good))
                for key in ('source_id', 'project_id', 'revision', 'content', 'provider'):
                    bad = copy.deepcopy(good)
                    bad['error']['details'] = {key: ID}
                    self.assertFalse(accepts(schema, bad), (path, status, key))
