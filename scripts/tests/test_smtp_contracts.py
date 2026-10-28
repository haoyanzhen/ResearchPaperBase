"""Approved single SMTP service, provider credentials and safe OAuth transport."""
import copy
import unittest
from test_api_contracts import SCHEMAS, SPEC_DATA, valid


class SMTPContracts(unittest.TestCase):
    def test_save_supports_oauth_application_without_plaintext_token_fields(self):
        value = {'sender_email': 'a@example.invalid', 'server': 'smtp.gmail.com',
                 'port': 587, 'encryption': 'starttls', 'auth_type': 'token',
                 'provider': 'gmail', 'username': 'a@example.invalid',
                 'expected_revision': 'revision',
                 'oauth': {'client_id': 'registered-client', 'tenant': None,
                           'client_secret': {'operation': 'set', 'value': 'new-input'}}}
        check = lambda value: valid('SMTPSave', value)
        self.assertTrue(check(value))
        for key in ['access_token', 'refresh_token', 'authorization_code', 'token_url']:
            bad = copy.deepcopy(value)
            bad['oauth'][key] = 'must-not-be-a-generic-input'
            self.assertFalse(check(bad), key)

    def test_oauth_view_cannot_expose_saved_credentials(self):
        value = {'client_id': 'client', 'tenant': None,
                 'client_secret': {'configured': True, 'hint': None}}
        check = lambda value: valid('SMTPOAuthView', value)
        self.assertTrue(check(value))
        for field in ['value', 'refresh_token', 'access_token']:
            bad = copy.deepcopy(value)
            bad['client_secret'][field] = 'secret'
            self.assertFalse(check(bad))

    def test_singleton_task_target_and_callback_do_not_return_credentials(self):
        schema = SCHEMAS['SMTPTaskView']['properties']
        self.assertEqual(schema['operation_id'], {'const': 'Admin.TestSMTPConnection'})
        self.assertEqual(schema['target']['properties']['type'], {'const': 'system_smtp_config'})
        callback = SPEC_DATA['paths']['/admin/smtp-config/oauth/callback']['get']
        response = callback['responses']['303']
        self.assertNotIn('content', response)
        self.assertEqual(response['headers']['Location']['schema']['enum'], [
            '/workspace?smtp_oauth=connected', '/workspace?smtp_oauth=failed'])
        start = SPEC_DATA['paths']['/admin/smtp-config/oauth/start']['post']
        self.assertEqual(start['x-authorization'], 'enabled-admin')
        self.assertTrue({'X-CSRF-Token', 'Idempotency-Key'} <= {
            p['name'] for p in start['parameters'] if p.get('required')})
        self.assertNotIn('/admin/smtp-config/{config_id}', SPEC_DATA['paths'])
