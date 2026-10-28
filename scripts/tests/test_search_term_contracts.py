"""ST machine schemas reject scope expansion and preserve explicit review."""
import copy
import unittest
from test_api_contracts import SCHEMAS, SPEC_DATA, valid


class SearchTermContracts(unittest.TestCase):
    def test_st01_term_fields_are_closed_and_sources_explicit(self):
        self.assertTrue(valid('SearchTermWrite', {'query': 'A AND B'}))
        for value in [{'query': ''}, {'query': 'a', 'enabled': True},
                      {'query': 'a', 'source_policy': {'mode': 'selected', 'source_refs': []}},
                      {'query': 'a', 'auto_update_enabled': None}]:
            self.assertFalse(valid('SearchTermWrite', value))
        policy = {'mode': 'selected', 'source_refs': [
            {'source': 'user', 'config_id': '00000000-0000-4000-8000-000000000001'}]}
        self.assertTrue(valid('TermSourcePolicy', policy))
        policy['source_refs'] *= 2
        self.assertFalse(valid('TermSourcePolicy', policy))

    def test_st04_generation_has_no_overwrite_authorization(self):
        body = {'expected_revision': 'r', 'model_selection': {'source': 'user',
                'config_id': '00000000-0000-4000-8000-000000000001', 'model_id': 'm'},
                'acknowledged_risk_ids': []}
        self.assertTrue(valid('TermGenerationCommand', body))
        self.assertFalse(valid('TermGenerationCommand', body | {'confirmation_token': 'overwrite'}))
        props = SCHEMAS['TermGenerationTaskView']['properties']
        self.assertEqual(props['operation_id'], {'const': 'Construction.GenerateTerms'})
        self.assertEqual(props['target']['properties']['type'], {'const': 'construction_workspace'})
        self.assertEqual(props['project_id'], {'$ref':'#/components/schemas/ID'})
        self.assertEqual(props['knowledge_version_id'], {'type':'null'})

    def test_st05_discard_has_no_candidate_body(self):
        value = {'id':'00000000-0000-4000-8000-000000000001', 'revision':'r',
                 'status':'discarded', 'discarded_at':'2026-10-28T00:00:00Z'}
        self.assertTrue(valid('DiscardedTermView', value))
        self.assertFalse(valid('DiscardedTermView', value | {'query':'private candidate'}))
        for suffix in ['', '/{term_id}', '/{term_id}/confirm', '/{term_id}/discard', '/generate']:
            self.assertIn('/projects/{project_id}/construction-workspace/search-terms'+suffix, SPEC_DATA['paths'])
