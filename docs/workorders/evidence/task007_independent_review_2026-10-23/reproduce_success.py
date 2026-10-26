"""Read-only counterexample: classification mutation returning unconfirmed success."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'scripts/tests'))
from test_material_policy_contracts import SPEC_DATA, VIEW, ID, accepts

for action in ('confirm', 'correct'):
    path = '/projects/{project_id}/material-sources/{source_id}/classification/' + action
    schema = SPEC_DATA['paths'][path]['post']['responses']['200']['content']['application/json']['schema']
    value = {'data': VIEW, 'meta': {'request_id': ID}}
    print(action, 'unconfirmed 200 accepted:', accepts(schema, value))

from test_material_policy_contracts import FACT
for action in ('confirm', 'correct'):
    path = '/projects/{project_id}/material-sources/{source_id}/classification/' + action
    schema = SPEC_DATA['paths'][path]['post']['responses']['200']['content']['application/json']['schema']
    confirmed = VIEW | {'confirmation_status': 'confirmed', 'confirmation': FACT}
    for meta in ({'request_id': ID}, {'request_id': ID, 'idempotency_expires_at': None}):
        print(action, 'confirmed 200 meta', meta, 'accepted:', accepts(schema, {'data': confirmed, 'meta': meta}))
