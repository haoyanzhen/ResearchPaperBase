"""A04 requirement examples: fixed expectations from 04/08, not schema-derived inputs."""
import copy
import json
import unittest
from pathlib import Path
from test_api_contracts import valid, SPEC_DATA, SCHEMAS

# Explicit normative examples also ensure every published variant is exercised.
GROUPS = [
 (400,'validation','VALIDATION_BAD_REQUEST VALIDATION_CURSOR_MISMATCH VALIDATION_CURSOR_EXPIRED'),
 (401,'auth','AUTH_REQUIRED AUTH_SESSION_INVALID AUTH_ACCOUNT_DISABLED AUTH_INVALID_CREDENTIALS'),
 (403,'permission','PERMISSION_ADMIN_REQUIRED PERMISSION_CSRF_REJECTED'),
 (404,'permission','PERMISSION_RESOURCE_UNAVAILABLE'),
 (409,'state','STATE_OPERATION_NOT_ALLOWED STATE_PROJECT_READ_ONLY STATE_NOT_CANCELLABLE STATE_LAST_ADMIN_REQUIRED STATE_IDEMPOTENCY_CONFLICT STATE_CONFIRMATION_STALE STATE_CONFIRMATION_REQUIRED STATE_EVENT_REPLAY_UNAVAILABLE'),
 (409,'lock_conflict','LOCK_CONSTRUCTION_OCCUPIED LOCK_RESPONSE_ACTIVE LOCK_CONTENT_BUSY'),
 (409,'version','VERSION_REQUIRED VERSION_BINDING_MISMATCH VERSION_BASELINE_STALE'),
 (409,'configuration','CONFIG_MODEL_SELECTION_REQUIRED CONFIG_MISSING CONFIG_SECRET_UNAVAILABLE CONFIG_SOURCE_DISABLED CONFIG_CONNECTION_FAILED'),
 (410,'storage','STORAGE_FILE_UNAVAILABLE'),(412,'state','STATE_REVISION_CONFLICT'),(428,'state','STATE_REVISION_REQUIRED'),
 (413,'validation','VALIDATION_PAYLOAD_TOO_LARGE'),(415,'validation','VALIDATION_UNSUPPORTED_FORMAT'),
 (422,'validation','VALIDATION_FIELD_INVALID VALIDATION_UNKNOWN_FIELD VALIDATION_FILE_UNREADABLE'),
 (429,'state','STATE_RESOURCE_LIMIT'),(502,'provider','PROVIDER_FAILED'),(503,'provider','PROVIDER_UNAVAILABLE'),(504,'provider','PROVIDER_TIMEOUT'),(500,'storage','STORAGE_INTERNAL_FAILURE')]
CASES=[(code,status,category) for status,category,codes in GROUPS for code in codes.split()]
RID='00000000-0000-4000-8000-000000000002'
def error(code,category):
 return dict(code=code,category=category,message='资源不可用' if code=='PERMISSION_RESOURCE_UNAVAILABLE' else '操作未完成',retryable=False,details=({'status_url': '/api/v1/tasks/' + RID} if code == 'STATE_EVENT_REPLAY_UNAVAILABLE' else None),recovery=None)
def action(name,label): return dict(action=name,label=label)

class PublicErrorTests(unittest.TestCase):
 def test_er01_every_variant_required_null_types_unknown_and_category(self):
  published={SCHEMAS[r['$ref'].rsplit('/',1)[1]]['properties']['code']['const'] for r in SCHEMAS['PublicError']['oneOf']}
  self.assertEqual(published,{c[0] for c in CASES})
  for code,status,cat in CASES:
   with self.subTest(code=code):
    value=error(code,cat); self.assertTrue(valid('PublicError',value))
    for key in value:
     missing=copy.deepcopy(value); del missing[key]; self.assertFalse(valid('PublicError',missing),key)
     wrong=copy.deepcopy(value); wrong[key]=[]; self.assertFalse(valid('PublicError',wrong),key)
    for change in [{'extra':'private'},{'category':'invented'},{'code':'NEW_UNKNOWN'},{'retryable':True},{'recovery':action('rerun','重新运行')}]:
     self.assertFalse(valid('PublicError',value|change))
    envelope={'error':value,'meta':{'request_id':RID}}
    self.assertTrue(valid('ErrorEnvelope',envelope))
    self.assertTrue(valid('ErrorEnvelope'+str(status),envelope))
    self.assertFalse(valid('ErrorEnvelope'+str(404 if status!=404 else 500),envelope))
    self.assertFalse(valid('ErrorEnvelope',{'error':value,'meta':{}}))
 def test_er02_unavailable_indistinguishable(self):
  # Synthetic internal causes map to exactly the same public value. No production mapper claimed.
  projections=[error('PERMISSION_RESOURCE_UNAVAILABLE','permission') for cause in ['missing','foreign_project','deleted','hidden']]
  self.assertTrue(all(v==projections[0] for v in projections))
  for field in ['project_id','exists','resource_url','owner_id','reason']:
   self.assertFalse(valid('PublicError',projections[0]|{'details':{field:'private-marker'}}))
  self.assertFalse(valid('PublicError',projections[0]|{'message':'Object exists in another project'}))
 def test_er03_closed_details_and_sanitization_limit(self):
  v=error('PROVIDER_FAILED','provider')
  for field in ['raw_response','sql','stack','api_key','path','value']:
   self.assertFalse(valid('PublicError',v|{'details':{field:'SYNTHETIC_PRIVATE_MARKER'}}))
  self.assertTrue(valid('PublicError',v|{'details':{'reason':'authentication'}}))
  self.assertFalse(valid('PublicError',v|{'details':{'reason':'SYNTHETIC_PRIVATE_MARKER'}}))
  # Free text cannot be proven sanitized by schema; deliberately keep this limitation visible.
  self.assertTrue(valid('PublicError',v|{'message':'SYNTHETIC_PRIVATE_MARKER'}))
 def test_er04_revision_confirmation_and_no_overwrite(self):
  v=error('STATE_REVISION_CONFLICT','state')
  details={'current_revision':'r2','resource_url':'/api/v1/projects/'+RID}
  self.assertTrue(valid('PublicError',v|{'details':details,'recovery':action('reload_resource','重新读取')}))
  for field in details:
   bad=details.copy(); del bad[field]; self.assertFalse(valid('PublicError',v|{'details':bad}))
  for url in ['https://evil.test','/private/secret','/api/v1/../secret','/api/v1/tasks/x?token=secret']:
   self.assertFalse(valid('PublicError',v|{'details':details|{'resource_url':url}}))
  for code in ['STATE_CONFIRMATION_REQUIRED','STATE_CONFIRMATION_STALE']:
   e=error(code,'state'); self.assertTrue(valid('PublicError',e|{'recovery':action('refresh_confirmation','重新查看确认依据')}))
   self.assertFalse(valid('PublicError',e|{'recovery':action('retry_request','按原请求条件重试')}))
  self.assertFalse(valid('PublicError',v|{'details':details|{'force':True}}))
 def test_er05_submission_unknown_and_safe_retry(self):
  for code,cat in [('STORAGE_INTERNAL_FAILURE','storage'),('PROVIDER_FAILED','provider'),('PROVIDER_TIMEOUT','provider'),('PROVIDER_UNAVAILABLE','provider'),('STATE_RESOURCE_LIMIT','state')]:
   v=error(code,cat)
   known=v|{'details':{'outcome':'not_accepted'},'retryable':True,'recovery':action('retry_request','按原请求条件重试')}
   unknown=v|{'details':{'outcome':'unknown'},'recovery':action('check_result','核查原操作结果')}
   self.assertTrue(valid('PublicError',known)); self.assertTrue(valid('PublicError',unknown))
   for bad in [unknown|{'retryable':True},unknown|{'recovery':None},known|{'details':None},known|{'details':{'outcome':'unknown'}},known|{'recovery':None}]:
    self.assertFalse(valid('PublicError',bad))
   for forbidden in ['new_key','regenerate','retry_run','reconnect','force']:
    self.assertFalse(valid('PublicError',unknown|{'recovery':action(forbidden,'执行')}))
 def test_er06_named_details_and_action_boundaries(self):
  examples=[('VALIDATION_FIELD_INVALID','validation',{'fields':[{'field':'model_selection.model_id','reason':'required'}]},'correct_request','修正请求'),
   ('STATE_EVENT_REPLAY_UNAVAILABLE','state',{'status_url':'/api/v1/tasks/'+RID},'reload_task','重新读取状态'),
   ('CONFIG_CONNECTION_FAILED','configuration',{'reason':'network'},'repair_configuration','检查配置')]
  for code,cat,details,a,label in examples:
   v=error(code,cat)|{'details':details,'recovery':action(a,label)}
   self.assertTrue(valid('PublicError',v))
   self.assertFalse(valid('PublicError',v|{'details':details|{'private':'marker'}}))
   self.assertFalse(valid('PublicError',v|{'recovery':action(a,label)|{'url':'https://evil.test'}}))
   for k in details:
    bad=details.copy(); del bad[k]; self.assertFalse(valid('PublicError',v|{'details':bad}))
  for code,cat,a,label in [('AUTH_REQUIRED','auth','reauthenticate','重新认证'),('PERMISSION_CSRF_REJECTED','permission','refresh_csrf','刷新请求凭据'),('VALIDATION_CURSOR_EXPIRED','validation','reload_page','重新读取第一页')]:
   self.assertTrue(valid('PublicError',error(code,cat)|{'recovery':action(a,label)}))
  self.assertFalse(valid('ErrorFieldsDetails',{'fields':[]}))
  self.assertFalse(valid('ErrorFieldsDetails',{'fields':[{'field':'password','reason':'invalid','value':'secret'}]}))
 def test_er07_shared_carriers_not_task_http_failure(self):
  e=error('PROVIDER_UNAVAILABLE','provider')
  self.assertTrue(valid('ErrorEnvelope',{'error':e,'meta':{'request_id':RID}}))
  self.assertTrue(valid('ErrorPayload',{'error':e}))
  self.assertTrue(valid('TaskError',e))  # Task.error only; no fabricated complete Task schema.
  unsafe=e|{'details':{'outcome':'not_accepted'},'retryable':True,'recovery':action('retry_request','按原请求条件重试')}
  self.assertTrue(valid('PublicError',unsafe))
  self.assertFalse(valid('TaskError',unsafe))
  self.assertFalse(valid('ErrorPayload',{'error':unsafe}))
  self.assertEqual(SPEC_DATA['x-sse-payloads']['error'],'#/components/schemas/ErrorPayload')
  self.assertNotIn('TaskView',SCHEMAS)
 def test_er08_existing_requests_success_and_bindings_preserved(self):
  root=Path(__file__).resolve().parents[2]
  old=json.loads((root/'docs/workorders/evidence/a04_2026-10-22/reviewed-p0.openapi.json').read_text())
  llm_changed={'ModelParameters','LLMWrite','LLMPatch','LLMView','ConnectionTest'}
  for name,schema in old['components']['schemas'].items():
   if name in {'SourceWrite','SourcePatch','SourceView'}:
    # task027 user decision only adds this exact address-role documentation.
    updated=copy.deepcopy(SCHEMAS[name])
    self.assertEqual(updated['properties']['base_url'].pop('description'), '检索服务/API入口，由已实现的Provider适配器解释；具体论文、网页或文件地址属于检索结果或手动补充资料，不属于数据源配置。')
    self.assertEqual(schema,updated,name)
   elif name in {'SMTPWrite','SMTPSave','SMTPView'}:
    # D-SMTP-02/03 explicitly authorize provider-specific OAuth; normalize only additions.
    updated=copy.deepcopy(SCHEMAS[name])
    self.assertEqual(updated['properties'].pop('provider')['enum'], ['custom','qq','163','gmail','microsoft365','sendgrid'])
    oauth=updated['properties'].pop('oauth')
    self.assertEqual(oauth, {'anyOf':[{'$ref':'#/components/schemas/'+('SMTPOAuthView' if name=='SMTPView' else 'SMTPOAuthWrite')},{'type':'null'}]})
    if name=='SMTPView':
     self.assertEqual(updated['properties'].pop('oauth_status')['enum'], ['not_connected','connected','reauthorization_required','refreshing'])
     self.assertEqual(updated['properties'].pop('connection_status')['enum'], ['untested','available','unavailable'])
     self.assertEqual(updated['properties'].pop('last_test_at'), {'anyOf':[{'$ref':'#/components/schemas/Time'},{'type':'null'}]})
     for added in ['provider','oauth','oauth_status','connection_status','last_test_at']: updated['required'].remove(added)
    self.assertEqual(schema,updated,name)
   elif name not in llm_changed: self.assertEqual(schema,SCHEMAS[name],name)
   else:
    # task026 explicitly accepted expansion; LP and LC13 test its new bounded contracts.
    self.assertFalse(SCHEMAS[name]['additionalProperties'])
    self.assertTrue(set(schema['properties']) <= set(SCHEMAS[name]['properties']))
  for path,item in old['paths'].items():
   for method,op in item.items():
    updated=copy.deepcopy(SPEC_DATA['paths'][path][method]); updated['x-errors']=op['x-errors']
    if method == 'get' and (path.startswith('/me/llm-configs') or path in {'/me/model-options','/me/model-selection'}):
     guard=next(p for p in updated['parameters'] if p['name']=='X-Expected-Actor')
     self.assertEqual(guard, {'name':'X-Expected-Actor','in':'header','required':False,'schema':{'type':'string','format':'uuid'}})
     updated['parameters'].remove(guard)
    if method == 'post' and path in {'/me/llm-configs/{config_id}/test','/admin/llm-configs/{config_id}/test'}:
     self.assertEqual(updated['requestBody']['content']['application/json']['schema'],{'$ref':'#/components/schemas/LLMTestRequest'})
     updated['requestBody']=copy.deepcopy(op['requestBody'])
    if method == 'post' and path in {'/me/llm-configs/{config_id}/test','/me/llm-configs/{config_id}/models/refresh'}:
     self.assertEqual(updated['responses']['202']['content']['application/json']['schema']['properties']['data'],{'$ref':'#/components/schemas/LLMTaskView'})
     del updated['responses']['202']; updated['x-coverage']=op['x-coverage']
    if method == 'post' and path in {'/admin/llm-configs/{config_id}/test','/admin/llm-configs/{config_id}/models/refresh'}:
     # task031 adds a scoped system projection; retain every historical binding.
     self.assertEqual(updated['responses']['202']['content']['application/json']['schema']['properties']['data'],{'$ref':'#/components/schemas/SystemLLMTaskView'})
     del updated['responses']['202']; updated['x-coverage']=op['x-coverage']
    if method == 'post' and path == '/admin/smtp-config/test':
     self.assertEqual(updated['responses']['202']['content']['application/json']['schema']['properties']['data'],{'$ref':'#/components/schemas/SMTPTaskView'})
     del updated['responses']['202']; updated['x-coverage']=op['x-coverage']
    if method == 'post' and path == '/admin/data-source-configs/{config_id}/test':
     self.assertEqual(updated['responses']['202']['content']['application/json']['schema']['properties']['data'],{'$ref':'#/components/schemas/SystemSourceTaskView'})
     del updated['responses']['202']; updated['x-coverage']=op['x-coverage']
    if method == 'post' and path == '/me/data-source-configs/{config_id}/test':
     self.assertEqual(updated['responses']['202']['content']['application/json']['schema']['properties']['data'],{'$ref':'#/components/schemas/SourceTaskView'})
     del updated['responses']['202']; updated['x-coverage']=op['x-coverage']
    if (path, method) in {
        ('/projects/{project_id}/construction-workspace', 'patch'),
        ('/projects/{project_id}/construction-workspace/search-terms/{term_id}/confirm', 'post')}:
     # task037 promotes exactly these request-only endpoints to bounded responses.
     expected = 'ConstructionWorkspaceView' if method == 'patch' else 'SearchTermView'
     self.assertEqual(updated['responses']['200']['content']['application/json']['schema']['properties']['data'], {'$ref':'#/components/schemas/'+expected})
     self.assertEqual(set(updated['responses']), {'200','400','401','403','404','409','412','413','415','422','428','500'})
     for status in ['400','401','403','404','409','412','413','415','422','428','500']:
      self.assertEqual(updated['responses'][status], {'$ref':'#/components/responses/PublicError'+status})
     guard=next(p for p in updated['parameters'] if p['name']=='X-Expected-Actor')
     self.assertEqual(guard, {'name':'X-Expected-Actor','in':'header','required':False,'schema':{'$ref':'#/components/schemas/ID'}})
     updated['parameters'].remove(guard)
     updated['responses']=copy.deepcopy(op['responses']); updated['x-coverage']=op['x-coverage']
    if (path, method) == ('/projects', 'post'):
     # task014 owns these exact B01 additions; PC-01..08 verify their new requirements.
     # Normalize only reviewed deltas, then retain the full historical operation assertion.
     del updated['x-contract-slice']; del updated['x-error-codes']
     next(p for p in updated['parameters'] if p['name']=='Idempotency-Key')['schema'].pop('not')
     for status in ('400','401','403','404','409','413','415','422','429','500'):
      del updated['responses'][status]
     updated['responses']['default']=copy.deepcopy(op['responses']['default'])
     success=updated['responses']['201']
     del success['headers']['Cache-Control']['required']; del success['headers']['Location']['required']
     success['content']['application/json']['schema']['properties']['meta']={'$ref':'#/components/schemas/IdempotentMeta'}
    if (path, method) == ('/projects', 'get'):
     # task021 owns the bounded cursor and optional actor consistency guard.
     # Assert the precise additions before normalizing for the historical check.
     guard=next(p for p in updated['parameters'] if p['name']=='X-Expected-Actor')
     self.assertEqual(guard['in'],'header'); self.assertFalse(guard['required'])
     self.assertEqual(guard['schema'],{'type':'string','format':'uuid'})
     updated['parameters'].remove(guard)
     cursor=next(p for p in updated['parameters'] if p['name']=='cursor')
     self.assertEqual(cursor['schema'].pop('maxLength'),2048)
    self.assertEqual(op,updated)
  self.assertEqual(SPEC_DATA['components']['responses']['PublicError429']['headers']['Retry-After']['required'],True)

if __name__=='__main__': unittest.main()
