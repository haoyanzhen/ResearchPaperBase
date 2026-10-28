"""Platform source diagnostics preserve their own operation and target scope."""
import copy
import unittest
from test_api_contracts import SCHEMAS, SPEC_DATA


class SystemSourceContracts(unittest.TestCase):
    def test_system_source_task_scope(self):
        expected = copy.deepcopy(SCHEMAS['SourceTaskView'])
        expected['properties']['operation_id'] = {'const': 'Admin.TestSystemSource'}
        expected['properties']['target']['properties']['type'] = {'const': 'system_data_source_config'}
        self.assertEqual(SCHEMAS['SystemSourceTaskView'], expected)
        operation = SPEC_DATA['paths']['/admin/data-source-configs/{config_id}/test']['post']
        self.assertEqual(operation['responses']['202']['content']['application/json']['schema']['properties']['data'], {'$ref': '#/components/schemas/SystemSourceTaskView'})
