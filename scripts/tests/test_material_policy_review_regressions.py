"""Task007 R01/R02: requirement-derived wire response fixtures, no runtime claims."""
import copy
import unittest

from test_material_policy_contracts import BASE, FACT, ID, POLICY, TIME, VIEW, accepts
from test_api_contracts import SPEC_DATA

CLASSIFICATION = BASE + '/material-sources/{source_id}/classification'
CONFIRMED = VIEW | {'confirmation_status': 'confirmed', 'confirmation': FACT}
META = {'request_id': ID, 'idempotency_expires_at': '2026-10-24T01:00:00Z'}


def response(path, method):
    return SPEC_DATA['paths'][path][method]['responses']['200']['content']['application/json']['schema']


class MaterialPolicyReviewRegressionTests(unittest.TestCase):
    def test_r01_each_mutation_requires_confirmed_fact(self):
        for action in ('confirm', 'correct'):
            schema = response(CLASSIFICATION + '/' + action, 'post')
            for classification in ('public', 'private'):
                good = CONFIRMED | {'classification': classification}
                with self.subTest(action=action, classification=classification):
                    self.assertTrue(accepts(schema, {'data': good, 'meta': META}))
                    self.assertFalse(accepts(schema, {'data': good | {'confirmation_status': 'unconfirmed', 'confirmation': None}, 'meta': META}))
                    self.assertFalse(accepts(schema, {'data': good | {'confirmation': None}, 'meta': META}))
                    for key in ('confirmation_status', 'confirmation'):
                        missing = dict(good)
                        del missing[key]
                        self.assertFalse(accepts(schema, {'data': missing, 'meta': META}))

    def test_r02_each_mutation_requires_nonnull_utc_expiry(self):
        for action in ('confirm', 'correct'):
            schema = response(CLASSIFICATION + '/' + action, 'post')
            self.assertTrue(accepts(schema, {'data': CONFIRMED, 'meta': META}))
            with self.subTest(action=action, expiry='missing'):
                self.assertFalse(accepts(schema, {'data': CONFIRMED, 'meta': {'request_id': ID}}))
            for expiry in (None, '', 1, True, {}, [], '2026-10-24', '2026-10-24T09:00:00+08:00', 'not-time'):
                with self.subTest(action=action, expiry=expiry):
                    self.assertFalse(accepts(schema, {'data': CONFIRMED, 'meta': META | {'idempotency_expires_at': expiry}}))
            self.assertTrue(accepts(schema, {'data': CONFIRMED, 'meta': META | {'original_request_id': ID}}))

    def test_r01_r02_read_and_policy_response_scope_preserved(self):
        for data in (VIEW, CONFIRMED):
            self.assertTrue(accepts(response(CLASSIFICATION, 'get'), {'data': data, 'meta': {'request_id': ID}}))
        for method in ('get', 'put'):
            self.assertTrue(accepts(response(BASE + '/material-policy', method), {'data': POLICY, 'meta': {'request_id': ID}}))
            self.assertTrue(accepts(response(BASE + '/material-policy', method), {'data': POLICY | {'mode': 'allow_private', 'risk_acknowledged_at': TIME}, 'meta': {'request_id': ID}}))

    def test_r01_r02_nested_fact_and_envelope_protection_preserved(self):
        for action in ('confirm', 'correct'):
            schema = response(CLASSIFICATION + '/' + action, 'post')
            good = {'data': CONFIRMED, 'meta': META}
            self.assertTrue(accepts(schema, good))
            for branch in ((), ('data',), ('meta',), ('data', 'confirmation')):
                bad = copy.deepcopy(good)
                node = bad
                for key in branch:
                    node = node[key]
                node['allow'] = True
                self.assertFalse(accepts(schema, bad))
            for key in ('basis', 'confirmed_by', 'confirmed_at'):
                bad = copy.deepcopy(good)
                del bad['data']['confirmation'][key]
                self.assertFalse(accepts(schema, bad))
