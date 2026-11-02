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
        self.assertEqual(SCHEMAS['RetrievalWaiting']['properties']['allowed_actions']['items'], {'enum': ['confirm_retrieval', 'confirm_screening', 'confirm_processing', 'confirm_analysis', 'confirm_ingestion_preview']})

    def test_cr03_default_rate_limit_is_nullable(self):
        source = dict(source='user', config_id=ID, provider='arxiv', config_revision=ID,
                      credential_revision=ID, enabled=True, access_mode='anonymous', rate_limit_per_minute=None)
        self.assertTrue(valid('TermSourceOption', source))
        self.assertFalse(valid('TermSourceOption', source | {'rate_limit_per_minute': 0}))

    def test_pp31_processing_shape_requires_attempts_and_consistent_text_basis(self):
        value = dict(status='failed', text_source_kind=None, failure_reason='no text',
                     participates_in_knowledge=False, selected_source_id=None, source_ids=[ID],
                     diagnostics=[], text_preview=None, source_attempts=[dict(source_id=ID, state='failed')],
                     basis=dict(processing_revision=ID, input_revision=ID, text_revision_id=None,
                                document_asset_id=None, file_revision=None, confirmed_revision=None))
        self.assertTrue(valid('RunPaperProcessing', value))
        self.assertFalse(valid('RunPaperProcessing', {k: v for k, v in value.items() if k != 'source_attempts'}))
        for patch in [dict(status='available'), dict(text_source_kind='abstract_fallback'),
                      dict(participates_in_knowledge=True), dict(secret='forbidden')]:
            self.assertFalse(valid('RunPaperProcessing', value | patch))
        degraded = value | dict(status='degraded', text_source_kind='abstract_fallback',
                               selected_source_id=ID, text_preview='Real abstract',
                               basis=value['basis'] | dict(text_revision_id=ID))
        self.assertTrue(valid('RunPaperProcessing', degraded))
        self.assertFalse(valid('RunPaperProcessing', degraded | dict(basis=degraded['basis'] | dict(document_asset_id=ID))))
