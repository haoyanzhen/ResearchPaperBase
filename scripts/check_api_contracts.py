#!/usr/bin/env python3
"""Check the bounded API contract; never starts an application or contacts providers."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'contracts/p0.openapi.json'
COVERAGE = ROOT / 'contracts/p0.coverage.json'
OP_DOC = ROOT / 'docs/design/04-01_p0_operation_contracts.md'
METHODS = {'get', 'post', 'put', 'patch', 'delete'}


def operation_rows():
    """Track every operation-table row plus explicitly named prose-only routes.

    A source signature change requires deliberate coverage reclassification. Line numbers
    are intentionally excluded so editorial insertions do not create false drift.
    """
    rows = []
    for line in OP_DOC.read_text().splitlines():
        cols = re.split(r'(?<!\\)\|', line)
        if len(cols) < 4 or not re.search(r'`[A-Z][A-Za-z]+\.', cols[2]):
            continue
        rows.append({'signature': cols[1].strip(), 'use_cases': cols[2].strip()})
    # Prose-only route inventories: a change/addition/deletion is detected by extraction.
    for filename in ['04-01_p0_operation_contracts.md', '04-02_transport_task_file_contracts.md']:
        for match in re.finditer(r'`(GET|POST|PUT|PATCH|DELETE) ([^`\s]+)`',
                                (OP_DOC.parent / filename).read_text()):
            entry = {'signature': match.group(0)[1:-1], 'use_cases': filename}
            if entry not in rows:
                rows.append(entry)
    return rows


def operations(spec):
    return {(method, path): op for path, item in spec['paths'].items()
            for method, op in item.items() if method in METHODS}


def resolve_refs(value, spec):
    if isinstance(value, dict):
        if '$ref' in value:
            ref = value['$ref']
            assert ref.startswith('#/'), f'external reference is not allowed: {ref}'
            node = spec
            for token in ref[2:].split('/'):
                node = node[token.replace('~1', '/').replace('~0', '~')]
        for item in value.values():
            resolve_refs(item, spec)
    elif isinstance(value, list):
        for item in value:
            resolve_refs(item, spec)


def check(spec, coverage):
    from openapi_spec_validator import validate
    from jsonschema import Draft202012Validator
    validate(spec)
    resolve_refs(spec, spec)
    assert coverage['source_rows'] == operation_rows(), 'operation documentation drift: reclassify coverage'
    ids = set()
    for (method, path), op in operations(spec).items():
        assert op['operationId'] not in ids, 'duplicate operationId'
        ids.add(op['operationId'])
        assert op['x-phase'] == 'P0'
        assert op['x-use-case'] and op['x-fr'] and op['x-authorization']
        assert op['x-version-binding'] in {'not-applicable','bound-object','explicit-or-default-at-creation'}
        assert op['x-errors'] == '#/components/schemas/PublicError', 'public error reference drift'
        names = {p['name'] for p in op.get('parameters', [])}
        required_headers = {p['name'] for p in op.get('parameters', []) if p['in'] == 'header' and p.get('required') is True}
        assert set(re.findall(r'{([^}]+)}', path)) <= names, path
        if method != 'get':
            assert 'X-CSRF-Token' in required_headers, op['operationId']
        if method == 'post' and not path.startswith('/auth/') and not path.endswith(('/action-preview', '/association-clear-preview')):
            assert 'Idempotency-Key' in required_headers, op['operationId']
        if path.startswith('/admin/'):
            assert op['x-authorization'] == 'enabled-admin'
        if path.startswith('/projects/'):
            assert op['x-authorization'] == ('project-owner-readable' if method == 'get' else 'project-owner-active')
        assert op['security'] == ([] if path in ['/auth/csrf', '/auth/register', '/auth/login'] else [{'sessionCookie': []}])
        if 'x-material-policy' in op:
            assert set(op['responses']) == {'200'} | set(op['x-error-codes']), 'material error status drift'
            for status, codes in op['x-error-codes'].items():
                schema = op['responses'][status]['content']['application/json']['schema']
                expected = [
                    {'$ref': '#/components/schemas/ErrorEnvelope' + status},
                    {'properties': {'error': {'properties': {'code': {'enum': codes}}}}},
                ]
                assert schema == {'allOf': expected}, 'material error binding drift'
            assert op['operationId'] in coverage['material_policy']['operations'], 'material coverage drift'
            assert coverage['operation_coverage'][op['operationId']]['status'] == 'request-success-errors-partial'
    # B01 operation binding guard; expected semantic examples live in requirement tests.
    create = spec['paths']['/projects']['post']
    assert create.get('x-contract-slice') == 'project-create-b01', 'Project.Create binding missing'
    codes = coverage['project_create']['error_codes']
    assert create.get('x-error-codes') == codes, 'Project.Create error inventory drift'
    assert set(create['responses']) == {'201'} | set(codes), 'Project.Create status drift'
    assert coverage['operation_coverage']['Project.Create'] == {
        'status': 'request-success-errors-partial', 'gaps': ['GAP-RUNTIME']}, 'Project.Create coverage drift'
    for status, response in create['responses'].items():
        assert response.get('headers', {}).get('Cache-Control') == {
            'required': True, 'schema': {'type': 'string', 'const': 'no-store'}}, 'Project.Create cache drift'
        if status != '201':
            assert response['content']['application/json']['schema'] == {'allOf': [
                {'$ref': '#/components/schemas/ErrorEnvelope' + status},
                {'properties': {'error': {'properties': {'code': {'enum': codes[status]}}}}},
            ]}, 'Project.Create error binding drift'
    success = create['responses']['201']
    assert success['headers']['Location'].get('required') is True, 'Project.Create Location drift'
    assert success['content']['application/json']['schema']['properties']['meta'] == {
        '$ref': '#/components/schemas/ProjectCreateMeta'}, 'Project.Create expiry binding drift'
    assert spec['components']['schemas']['ProjectCreateMeta']['allOf'] == [
        {'$ref': '#/components/schemas/IdempotentMeta'},
        {'properties': {'idempotency_expires_at': {'$ref': '#/components/schemas/Time'}}},
    ], 'Project.Create expiry schema drift'
    assert create['responses']['429']['headers']['Retry-After'] == spec['components']['responses']['PublicError429']['headers']['Retry-After'], 'Project.Create Retry-After drift'
    assert sorted(ids) == sorted(coverage['typed_operations'] + coverage['request_only_operations']), 'coverage/spec operation mismatch'
    assert len(coverage['row_coverage']) == len(coverage['source_rows'])
    for index, row in enumerate(coverage['row_coverage']):
        assert row['source_row_index'] == index
        assert row['typed_operations'] or row['remaining'], 'unclassified operation row'
        assert set(row['typed_operations']) <= ids
    for name, expected in coverage['normative_fingerprints'].items():
        actual = hashlib.sha256((OP_DOC.parent / name).read_bytes()).hexdigest()
        assert actual == expected, 'normative text changed; synchronize and review: ' + name
    def bounded(node, location='$'):
        if isinstance(node, dict):
            if node.get('type') == 'object' or (isinstance(node.get('type'), list) and 'object' in node['type']):
                capacity_map = (
                    location in {'$/components/schemas/' + name + '/properties/model_context_windows'
                                 for name in ('LLMWrite', 'LLMPatch', 'LLMView')}
                    and node.get('maxProperties') == 1000
                    and node.get('propertyNames') == {'type': 'string', 'minLength': 1, 'maxLength': 200, 'pattern': r'^\S(?:[\s\S]*\S)?(?![\s\S])'}
                    and node.get('additionalProperties') == {
                        'type': 'integer', 'minimum': 1, 'maximum': 2147483647}
                )
                assert capacity_map or ('properties' in node and node.get('additionalProperties') is False), f'unbounded object: {location}'
            for key, val in node.items():
                bounded(val, location + '/' + key)
        elif isinstance(node, list):
            for index, val in enumerate(node):
                bounded(val, location + '/' + str(index))
    # Includes inline request/response schemas, not just reusable components.
    bounded(spec)
    for schema in spec['components']['schemas'].values():
        Draft202012Validator.check_schema(schema)
    error_refs = spec['components']['schemas']['PublicError']['oneOf']
    variants = [spec['components']['schemas'][r['$ref'].rsplit('/', 1)[1]] for r in error_refs]
    assert sorted(v['properties']['code']['const'] for v in variants) == sorted(coverage['public_errors']['variants']), 'public error coverage drift'
    expected_members = {}
    for reference, variant in zip(error_refs, variants):
        status = str(variant['x-http-status'])
        expected_members.setdefault(status, []).append(reference['$ref'])
    # Compare multisets: omissions, extra members and duplicates must all fail.
    envelopes = {name.removeprefix('ErrorEnvelope'): schema
                 for name, schema in spec['components']['schemas'].items()
                 if re.fullmatch(r'ErrorEnvelope[0-9]{3}', name)}
    assert set(envelopes) == set(expected_members), 'public error status groups drift'
    for status, expected in expected_members.items():
        response = spec['components']['responses']['PublicError' + status]
        assert response['content']['application/json']['schema']['$ref'] == '#/components/schemas/ErrorEnvelope' + status
        actual = envelopes[status]['properties']['error']['oneOf']
        assert sorted(member['$ref'] for member in actual) == sorted(expected), 'public error status membership drift: ' + status
    assert set(coverage['event_payloads_typed']) == set(spec['x-sse-payloads'])


def compatibility(old, new):
    """Conservative gate: unchanged old contracts pass; any existing-node change needs review.

    New paths, operations and unused schemas may be added. Existing reachable schemas,
    headers, security, statuses, semantic extensions and enum changes all fail closed.
    It intentionally reports review-required changes, not a proof of incompatibility.
    """
    issues = []
    old_ops, new_ops = operations(old), operations(new)
    for key, value in old_ops.items():
        if key not in new_ops or value != new_ops[key]:
            issues.append('operation changed/removed: ' + key[0].upper() + ' ' + key[1])
    for name, value in old.get('components', {}).get('schemas', {}).items():
        if new.get('components', {}).get('schemas', {}).get(name) != value:
            issues.append('schema changed/removed (directional review required): ' + name)
    for key in ('servers', 'security', 'x-sse-payloads'):
        if old.get(key) != new.get(key):
            issues.append('global contract changed: ' + key)
    for key, value in old.get('components', {}).items():
        if key != 'schemas' and new.get('components', {}).get(key) != value:
            issues.append('shared component changed: ' + key)
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, help='previous reviewed OpenAPI JSON; changes fail closed')
    args = parser.parse_args()
    spec, coverage = json.loads(SPEC.read_text()), json.loads(COVERAGE.read_text())
    check(spec, coverage)
    if args.baseline:
        changes = compatibility(json.loads(args.baseline.read_text()), spec)
        if changes:
            raise SystemExit('\n'.join(changes))
    print(f"PASS: {len(coverage['typed_operations'])} request/success partial + {len(coverage['request_only_operations'])} request-only operations; {len(spec['components']['schemas'])} schemas; "
          f"{len(coverage['source_rows'])} inventoried source rows; {len(spec['x-sse-payloads'])}/6 SSE payload types")
    if not args.baseline:
        print('COMPATIBILITY NOT CHECKED: no prior reviewed --baseline supplied.')
    print('NOT VERIFIED: runtime authorization/state/transactions, runtime error sanitization/action eligibility, TaskView/output and uncovered operations; see coverage.')


if __name__ == '__main__':
    main()
