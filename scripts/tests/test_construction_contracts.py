"""Bounded retrieval contracts preserve closed input and private-field boundaries."""
import unittest
from test_api_contracts import SCHEMAS, SPEC_DATA, valid

ID = '00000000-0000-4000-8000-000000000001'

class RetrievalContracts(unittest.TestCase):
    def test_cr01_start_rejects_scope_expansion(self):
        body = {'selected_terms': [{'term_id': ID, 'confirmed_revision': ID}],
                'retrieval_range': {'published_from': None, 'published_until': None},
                'result_limit_per_source': 100,
                'model_selection': {'source': 'user', 'config_id': ID, 'model_id': 'm'}}
        self.assertTrue(valid('RetrievalRunStart', body))
        for patch in [{'mode': 'revision_only'}, {'selected_terms': []},
                      {'result_limit_per_source': True}, {'result_limit_per_source': 1001},
                      {'publish': True}, {'supplement_inputs': None}, {'graph_update_mode': []}]:
            self.assertFalse(valid('RetrievalRunStart', body | patch), patch)

    def test_cr02_pagination_and_secret_fields_are_closed(self):
        base = '/projects/{project_id}/construction-runs'
        for suffix in ['', '/{run_id}/candidates', '/{run_id}/input-revisions']:
            op = SPEC_DATA['paths'][base + suffix]['get']
            self.assertEqual(op['responses']['200']['content']['application/json']['schema']['properties']['meta'], {'$ref': '#/components/schemas/PageMeta'})
            self.assertTrue({'page_size', 'cursor'} <= {p.get('name') for p in op['parameters']})
        for name in ['RetrievalRunView', 'RetrievalRuntimeConfig', 'RetrievalCandidate']:
            self.assertFalse(SCHEMAS[name]['additionalProperties'])
            self.assertNotIn('secret', SCHEMAS[name]['properties'])
        self.assertEqual(SCHEMAS['RetrievalWaiting']['properties']['allowed_actions']['items'], {'const': 'confirm_retrieval'})

    def test_cr03_default_rate_limit_is_nullable(self):
        source = dict(source='user', config_id=ID, provider='arxiv', config_revision=ID,
                      credential_revision=ID, enabled=True, access_mode='anonymous', rate_limit_per_minute=None)
        self.assertTrue(valid('TermSourceOption', source))
        self.assertFalse(valid('TermSourceOption', source | {'rate_limit_per_minute': 0}))
