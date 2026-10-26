"""Accepted task026 expansion preserves bounded, typed configuration contracts."""
import unittest
from test_api_contracts import valid, SCHEMAS, SPEC_DATA


class LLMParameterContracts(unittest.TestCase):
    def test_lp_contract_types_and_reserved_fields(self):
        for value in [{}, {'temperature': 0, 'top_p': 1}, {'custom_params': {'thinkingConfig': {'includeThoughts': False, 'thinkingBudget': 0}}}]:
            self.assertTrue(valid('ModelParameters', value))
        for value in [{'temperature': True}, {'top_p': 2}, {'timeout_seconds': 30}, {'custom_params': {'model': 'override'}}, {'custom_params': {'thinking': {'url': 'x'}}}, {'seed': None}]:
            self.assertFalse(valid('ModelParameters', value))
        self.assertEqual(SCHEMAS['LLMTestRequest']['required'], ['model_id'])
        self.assertFalse(valid('LLMTestRequest', {}))
        self.assertTrue(valid('LLMTestRequest', {'model_id': 'model-a'}))
        self.assertFalse(valid('LLMTestRequest', {'model_id': 'model-a', 'expected_revision': 'x'}))

    def test_lc_contract_async_response_and_no_enable(self):
        for name in ['LLMWrite', 'LLMPatch', 'LLMView']:
            self.assertNotIn('enabled', SCHEMAS[name]['properties'])
            self.assertIn('timeout_seconds', SCHEMAS[name]['properties'])
        for path in ['/me/llm-configs/{config_id}/test', '/me/llm-configs/{config_id}/models/refresh']:
            self.assertIn('202', SPEC_DATA['paths'][path]['post']['responses'])
        self.assertNotIn('cancel', SCHEMAS['LLMTaskView']['properties'])
