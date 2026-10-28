"""AG machine contracts follow account governance requirements, not implementation rows."""
import unittest
from test_api_contracts import valid, SPEC_DATA

RID = '11111111-1111-4111-8111-111111111111'


class AdminAccountContracts(unittest.TestCase):
    def test_ag_request_action_parameters_and_confirmation(self):
        base = {'action': 'change_email', 'expected_revision': RID}
        self.assertFalse(valid('AdminAccountPreviewRequest', base))
        self.assertTrue(valid('AdminAccountPreviewRequest', base | {'email': 'a@example.invalid'}))
        self.assertFalse(valid('AdminAccountPreviewRequest', base | {'action': 'disable', 'email': 'a@example.invalid'}))
        update = {'action': 'disable', 'expected_revision': RID, 'confirmation_token': 'token', 'acknowledged_risk_ids': ['risk']}
        self.assertTrue(valid('AdminAccountUpdateRequest', update))
        for extra in [{'action': 'delete'}, {'force': True}, {'password': 'raw'}, {'acknowledged_risk_ids': ['risk', 'risk']}]:
            self.assertFalse(valid('AdminAccountUpdateRequest', update | extra))

    def test_ag_password_sensitive_replay_and_delete_shape(self):
        replay = {'reset_completed': True, 'password_disclosed': False, 'operation_id': RID}
        self.assertTrue(valid('AdminAccountResetResult', replay))
        self.assertFalse(valid('AdminAccountResetResult', replay | {'new_password': 'never-replay-this'}))
        self.assertTrue(valid('AdminAccountResetResult', replay | {'password_disclosed': True, 'new_password': 'new-random-password'}))
        self.assertFalse(valid('AdminAccountResetResult', replay | {'password_disclosed': True}))
        result = {'resource_id': RID, 'revision': RID, 'task': None}
        self.assertTrue(valid('AdminAccountCommandResult', result))
        self.assertFalse(valid('AdminAccountCommandResult', {'completed': True}))

    def test_ag_preview_no_idempotency_reset_requires_it(self):
        preview = SPEC_DATA['paths']['/admin/users/{user_id}/action-preview']['post']
        reset = SPEC_DATA['paths']['/admin/users/{user_id}/reset-password']['post']
        self.assertNotIn('Idempotency-Key', [p['name'] for p in preview['parameters']])
        self.assertIn('Idempotency-Key', [p['name'] for p in reset['parameters'] if p.get('required')])
        response = reset['responses']['200']['content']['application/json']['schema']
        self.assertEqual(response['properties']['meta'], {'$ref': '#/components/schemas/IdempotentMeta'})
        delete = SPEC_DATA['paths']['/admin/users/{user_id}']['delete']
        risks = next(p for p in delete['parameters'] if p['name'] == 'acknowledged_risk_ids')
        self.assertTrue(risks['explode'])
        self.assertEqual(risks['in'], 'query')
