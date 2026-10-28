"""System task projection must not silently inherit private target identity."""
import copy
import unittest
from test_api_contracts import SCHEMAS, SPEC_DATA


class SystemLLMContracts(unittest.TestCase):
    def test_projection_keeps_scope_and_operations(self):
        personal = SCHEMAS['LLMTaskView']['properties']
        system = SCHEMAS['SystemLLMTaskView']['properties']
        self.assertEqual(personal['target']['properties']['type'], {'const': 'user_llm_config'})
        self.assertEqual(system['target']['properties']['type'], {'const': 'system_llm_config'})
        self.assertEqual(system['operation_id']['enum'], ['Admin.TestSystemLLM', 'Admin.RefreshSystemModels'])
        original = copy.deepcopy(SCHEMAS['LLMTaskView'])
        original['properties']['target'] = SCHEMAS['SystemLLMTaskView']['properties']['target']
        original['properties']['operation_id'] = SCHEMAS['SystemLLMTaskView']['properties']['operation_id']
        self.assertEqual(original, SCHEMAS['SystemLLMTaskView'])

    def test_both_admin_operations_have_typed_accepted_response(self):
        for suffix in ['test', 'models/refresh']:
            op = SPEC_DATA['paths']['/admin/llm-configs/{config_id}/' + suffix]['post']
            self.assertEqual(op['responses']['202']['content']['application/json']['schema']['properties']['data'], {'$ref': '#/components/schemas/SystemLLMTaskView'})
            self.assertNotIn('enabled', SCHEMAS['LLMWrite']['properties'])
