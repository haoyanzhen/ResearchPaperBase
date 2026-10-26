"""Run from repository root; in-memory mutations only, never write source contracts."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path('scripts/tests').resolve()))
import test_material_policy_coverage as tests
import test_material_policy_contracts as helpers

original = tests.SPEC_DATA
cases = []
def case(label, method, mutate):
    changed = copy.deepcopy(original)
    mutate(changed)
    tests.SPEC_DATA = changed
    helpers.SCHEMAS = changed["components"]["schemas"]
    result = unittest.TestResult()
    tests.MaterialPolicyCoverageTests(method).run(result)
    assert result.failures and not result.errors, (label, result.errors)
    cases.append({'mutation': label, 'detected': True, 'assertion_failures': len(result.failures)})

policy = tests.BASE + '/material-policy'
confirm = tests.CLASSIFICATION + '/confirm'
case('request loses revision requirement', 'test_nt03_nt08_each_write_validates_actual_request_binding',
     lambda s: s['components']['schemas']['MaterialPolicyWrite']['required'].remove('expected_revision'))
case('CSRF marked optional', 'test_nt04_nt08_parameters_are_required_in_correct_locations',
     lambda s: s['paths'][policy]['put']['parameters'][1].update(required=False))
case('scope expands across projects', 'test_nt04_nt08_parameters_are_required_in_correct_locations',
     lambda s: s['paths'][policy]['get']['x-material-policy'].update(scope='global'))
case('success permits missing source', 'test_nt08_success_envelopes_and_nested_required_fields',
     lambda s: s['components']['schemas']['MaterialClassificationView']['required'].remove('source'))
case('readonly content revision unbounded', 'test_nt05_nt08_readonly_revisions_identities_and_fact_boundaries',
     lambda s: s['components']['schemas']['MaterialSourceIdentity']['properties'].update(content_revision={'type': 'string'}))
case('provenance loses trusted scope restrictions', 'test_nt06_provenance_variants_remain_bound_in_each_source_response',
     lambda s: s['components']['schemas']['MaterialProvenance'].pop('allOf'))
case('error response loses no-store', 'test_nt07_private_responses_never_advertise_shared_caching',
     lambda s: s['paths'][confirm]['post']['responses']['404']['headers'].pop('Cache-Control'))
tests.SPEC_DATA = original
helpers.SCHEMAS = original["components"]["schemas"]
print(json.dumps(cases, indent=2))
