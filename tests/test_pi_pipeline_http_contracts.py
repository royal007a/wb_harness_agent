"""HA-0067: real offline HTTP results, not real model/legal-quality evidence."""
import copy
import hashlib
import json

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from backend.service import ROOT
from test_pi_contract_pipeline import pdf_fixture
from test_pi_security_guard import policy
from test_product_contract_boundaries import snapshot
from test_read_surfaces import client


PREFIX = '/api/local/pi-contract-pipeline/'
OPERATIONS = [
    ('/api/local/pi/runtime', 'get', 'pi-admission', 'runtime_status', 'application/json'),
    (PREFIX + 'preview', 'post', 'pi-contract-pipeline', 'preview', 'application/json'),
    (PREFIX + 'review', 'post', 'pi-contract-pipeline', 'finding', 'application/json'),
    (PREFIX + 'security-check', 'post', 'pi-security-guard', 'response', 'application/json'),
    (PREFIX + 'review-stream', 'post', 'pi-contract-pipeline', 'stream_event', 'text/event-stream'),
]
STATIC = ROOT / 'specs/v1/openapi.yaml'


@pytest.fixture
def offline(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Offline pipeline must not execute a Run, sidecar, tool or Provider')
    service = client.app.state.service
    monkeypatch.setattr(service, 'execute', forbidden)
    monkeypatch.setattr(service.pi_contract_review.adapter, 'start_run', forbidden)
    yield client


def validators(c, op, *, request=False, error=False):
    path, method, stem, name, media = op
    sources, resources = {}, []
    for bundle in ['pi-admission', 'pi-contract-pipeline', 'pi-security-guard', 'core-contracts']:
        file = ROOT / 'specs/v1' / (bundle + '.schema.json')
        source = json.loads(file.read_text())
        sources[bundle] = source
        resources += [(file.as_uri(), Resource.from_contents(source)),
                      (source['$id'], Resource.from_contents(source))]
    registry = Registry().with_resources(resources)
    dynamic, static = c.get('/openapi.json').json(), yaml.safe_load(STATIC.read_text())
    checks = []
    for doc, p, base in [(dynamic, path, {}), (static, path.removeprefix('/api'), {'$id': STATIC.as_uri()})]:
        operation = doc['paths'][p][method]
        holder = operation.get('requestBody', {}) if request else operation['responses'].get('default' if error else '200', {})
        if '$ref' in holder:
            holder = doc['components']['responses'][holder['$ref'].split('/')[-1]]
        content = holder.get('content', {})
        expected_media = 'application/json' if request or error else media
        assert expected_media in content, ('missing/wrong media', p, expected_media)
        check = Draft202012Validator({**doc, **base, **content[expected_media].get('schema', {})}, registry=registry)
        assert not check.is_valid({}), ('empty payload accepted', p, request, error)
        checks.append(check)
    if error:
        stem, name = 'core-contracts', 'local_http_error'
    elif request:
        name = 'request' if stem == 'pi-security-guard' else 'http_request'
    assert name in sources[stem]['$defs'], ('source definition missing', name)
    checks.append(Draft202012Validator({'$defs': sources[stem]['$defs'], '$ref': '#/$defs/' + name}, registry=registry))
    return checks


def valid(c, op, value):
    checks = validators(c, op)
    for check in checks:
        check.validate(value)
        assert not check.is_valid({**value, 'extra': True})
        for field in value:
            assert not check.is_valid({k: v for k, v in value.items() if k != field}), field
    return checks


def pdf(c, text='software development source code. RAW_SENTINEL_67'):
    raw = pdf_fixture(text)
    response = c.post('/api/local/research-native/documents?name=contract67.pdf', content=raw,
                      headers={'Content-Type': 'application/pdf'})
    assert response.status_code == 201, response.text
    return response.json(), raw


def post(c, index, body, key='contract67', **headers):
    return c.post(OPERATIONS[index][0], json=body, headers={'Idempotency-Key': key, **headers})


@pytest.mark.parametrize('operation', OPERATIONS, ids=lambda o: o[3])
def test_pi_published_response_is_not_empty_or_wrong_media(offline, operation):
    validators(offline, operation)


@pytest.mark.parametrize('sensitive', [False, True])
def test_pdf_preview_finding_and_stream_are_real_bound_and_replayable(offline, sensitive):
    c = offline
    resource, raw = pdf(c, 'software development RAW_SENTINEL_67 ' + ('13812345678 foo@example.com' if sensitive else 'source code delivery'))
    body = {'resource_id': resource['id'], 'chunk_max_chars': 1000}
    preview = post(c, 1, body).json()
    checks = valid(c, OPERATIONS[1], preview)
    assert preview['source_sha256'] == hashlib.sha256(raw).hexdigest()
    assert preview['classification']['contract_type'] == '技术服务'
    assert preview['status'] == ('needs_human' if sensitive else 'ready_for_skill')
    assert preview['security']['status'] == ('needs_human' if sensitive else 'clear')
    assert len(preview['security']['hits']) == (2 if sensitive else 0)
    for check in checks:
        bad = copy.deepcopy(preview)
        bad['status'] = 'ready_for_skill' if sensitive else 'needs_human'
        assert not check.is_valid(bad), 'outer security status mismatch'
        bad = copy.deepcopy(preview)
        bad['security']['hits'] = [] if sensitive else [{'kind': '手机号', 'count': 1}]
        assert not check.is_valid(bad), 'security hits/status mismatch'
    finding = post(c, 2, body).json()
    valid(c, OPERATIONS[2], finding)
    assert finding['status'] == 'needs_human'
    assert finding['risk_level'] == ('high' if sensitive else 'medium')
    assert finding['source_resource_id'] == resource['id']
    assert finding['evidence_refs'] == [f"evidence://{resource['id']}/chunk-{chunk['index']}/{chunk['text_sha256']}" for chunk in preview['chunks']]
    stream = post(c, 4, body, Accept='text/event-stream')
    assert stream.status_code == 200, stream.text
    assert stream.headers['content-type'].startswith('text/event-stream')
    assert stream.headers['cache-control'] == 'no-store'
    assert stream.headers['x-accel-buffering'] == 'no'
    frames = [json.loads(block.removeprefix('data: ')) for block in stream.text.strip().split('\n\n')]
    assert [f['event'] for f in frames] == ['preview', 'finding', 'done']
    stream_preview = copy.deepcopy(preview)
    for chunk in stream_preview['chunks']:
        chunk['heading'] = f"chunk-{chunk['index']}"
    assert frames == [{'event': 'preview', 'data': stream_preview}, {'event': 'finding', 'data': finding},
                      {'event': 'done', 'data': {'model_calls': 0, 'external_calls': 0}}]
    for frame in frames:
        frame_checks = valid(c, OPERATIONS[4], frame)
        for check in frame_checks:
            for data in [{}, {'model_calls': 1, 'external_calls': 0}, {**frame['data'], 'raw': 'RAW_SENTINEL_67'}]:
                assert not check.is_valid({'event': frame['event'], 'data': data})
            other = frames[(frames.index(frame) + 1) % len(frames)]['data']
            assert not check.is_valid({'event': frame['event'], 'data': other})
            if frame['event'] == 'preview':
                bad = copy.deepcopy(frame)
                bad['data']['chunks'][0]['heading'] = 'RAW_SENTINEL_67'
                assert not check.is_valid(bad), 'stream headings must be sanitized labels'
    assert 'RAW_SENTINEL_67' not in stream.text
    assert '13812345678' not in stream.text and 'foo@example.com' not in stream.text
    before = snapshot(c)
    assert post(c, 1, body).json() == preview
    assert post(c, 2, body).json() == finding
    assert post(c, 4, body, Accept='text/event-stream').text == stream.text
    assert snapshot(c) == before
    changed = post(c, 4, {**body, 'chunk_max_chars': 2000}, Accept='text/event-stream')
    assert changed.status_code == 409
    assert snapshot(c) == before


@pytest.mark.parametrize('index', [1, 2, 4])
def test_http_projection_and_request_boundaries(offline, index):
    resource, _ = pdf(offline)
    body = {'resource_id': resource['id'], 'ignored_raw': 'DO_NOT_TRUST', 'chunk_max_chars': 1000}
    checks = validators(offline, OPERATIONS[index], request=True)
    for check in checks:
        check.validate(body)
        for amount in [999, 16001, True, 1.5, '1000']:
            assert not check.is_valid({**body, 'chunk_max_chars': amount})
    headers = {'Accept': 'text/event-stream'} if index == 4 else {}
    first = post(offline, index, body, **headers)
    assert first.status_code == 200
    before = snapshot(offline)
    second = post(offline, index, {**body, 'ignored_raw': 'CHANGED'}, **headers)
    assert second.status_code == 200 and second.content == first.content
    assert snapshot(offline) == before
    for amount in [999, 16001, True, 1.5, '1000']:
        result = post(offline, index, {**body, 'chunk_max_chars': amount}, key='bad-' + str(amount), **headers)
        assert result.status_code == 409 and result.json()['error']['code'] == 'PI_PIPELINE_CONTRACT_INVALID'
        for check in validators(offline, OPERATIONS[index], error=True):
            check.validate(result.json())
    assert post(offline, index, {**body, 'chunk_max_chars': 16000}, key='max-size', **headers).status_code == 200


@pytest.mark.parametrize('index', [1, 2, 4])
@pytest.mark.parametrize('case,status,code', [
    ('missing', 404, 'NOT_FOUND'), ('blank', 422, 'PDF_TEXT_EMPTY'),
    ('corrupt', 422, 'PDF_PARSE_FAILED'), ('csv', 422, 'PDF_RESOURCE_INVALID'),
    ('bad_json', 422, 'VALIDATION_ERROR'),
])
def test_pipeline_failures_are_json_and_never_publish_a_stream(offline, index, case, status, code):
    resource = 'res_missing'
    if case in {'blank', 'corrupt'}:
        raw = pdf_fixture('') if case == 'blank' else b'%PDF-1.7\nnot-a-pdf'
        response = offline.post('/api/local/research-native/documents?name=invalid.pdf', content=raw,
                                headers={'Content-Type': 'application/pdf'})
        assert response.status_code == 201
        resource = response.json()['id']
    elif case == 'csv':
        response = offline.post('/api/v1/resources?name=not-a-contract.csv', content=b'a,b\n1,2\n')
        assert response.status_code == 201
        resource = response.json()['id']
    before = snapshot(offline)
    if case == 'bad_json':
        result = offline.post(OPERATIONS[index][0], content='{', headers={
            'Content-Type': 'application/json', 'Accept': 'text/event-stream', 'Idempotency-Key': 'failure67'})
    else:
        result = post(offline, index, {'resource_id': resource}, Accept='text/event-stream')
    assert result.status_code == status, result.text
    assert result.headers['content-type'].startswith('application/json')
    assert result.json()['error']['code'] == code
    for check in validators(offline, OPERATIONS[index], error=True):
        check.validate(result.json())
    assert snapshot(offline) == before


@pytest.mark.parametrize('index', [1, 2, 3, 4])
def test_non_json_body_uses_current_error_envelope(offline, index):
    before = snapshot(offline)
    result = offline.post(OPERATIONS[index][0], content='{}', headers={
        'Content-Type': 'text/plain', 'Accept': 'text/event-stream', 'Idempotency-Key': 'media67'})
    assert result.status_code == 415
    for check in validators(offline, OPERATIONS[index], error=True):
        check.validate(result.json())
    assert snapshot(offline) == before


def test_pi_static_dynamic_bindings_headers_and_request_schema_agree(offline):
    dynamic = offline.get('/openapi.json').json()
    static = yaml.safe_load(STATIC.read_text())
    namespaces = {'pi-admission': 'pi_admission_', 'pi-contract-pipeline': 'pi_pipeline_', 'pi-security-guard': 'pi_guard_'}
    for op in OPERATIONS:
        path, method, stem, name, media = op
        d = dynamic['paths'][path][method]
        s = static['paths'][path.removeprefix('/api')][method]
        assert d['responses']['200']['content'] == {media: {'schema': {'$ref': '#/components/schemas/' + namespaces[stem] + name}}}
        assert set(s['responses']['200']['content']) == {media}
        static_schema = s['responses']['200']['content'][media]['schema']
        if static_schema['$ref'].startswith('#/'):
            static_schema = static['components']['schemas'][static_schema['$ref'].split('/')[-1]]
        assert static_schema == {'$ref': './' + stem + '.schema.json#/$defs/' + name}
        assert d['responses']['default']['content']['application/json']['schema'] == {'$ref': '#/components/schemas/local_http_error'}
        assert s['responses']['default'] == {'$ref': '#/components/responses/LocalProductError'}
        if method == 'post':
            assert d['requestBody']['required'] is s['requestBody']['required'] is True
            expected = 'request' if stem == 'pi-security-guard' else 'http_request'
            assert d['requestBody']['content']['application/json']['schema'] == {'$ref': '#/components/schemas/' + namespaces[stem] + expected}
            static_request = s['requestBody']['content']['application/json']['schema']
            assert static['components']['schemas'][static_request['$ref'].split('/')[-1]] == {'$ref': './' + stem + '.schema.json#/$defs/' + expected}
        if media == 'text/event-stream':
            assert d['responses']['200']['headers'] == s['responses']['200']['headers'] == {
                'Cache-Control': {'schema': {'const': 'no-store'}}, 'X-Accel-Buffering': {'schema': {'const': 'no'}}}
            for operation in [d, s]:
                accept = next(p for p in operation['parameters'] if p.get('name') == 'Accept')
                assert accept['required'] is True
                assert accept['schema'] == {'type': 'string', 'pattern': 'text/event-stream'}
@pytest.mark.parametrize('index,maximum', [(1, 128), (2, 128), (3, 128), (4, 120)])
def test_idempotency_key_limits_match_actual_endpoint(offline, index, maximum):
    resource, _ = pdf(offline)
    body = {'action': {'phase': 'context'}, 'policy': policy()} if index == 3 else {'resource_id': resource['id']}
    headers = {'Accept': 'text/event-stream'} if index == 4 else {}
    assert post(offline, index, body, key='k' * maximum, **headers).status_code == 200
    for key in ['', 'k' * (maximum + 1)]:
        before = snapshot(offline)
        result = post(offline, index, body, key=key, **headers)
        assert result.status_code == 422
        assert snapshot(offline) == before
    docs = [(offline.get('/openapi.json').json(), OPERATIONS[index][0]),
            (yaml.safe_load(STATIC.read_text()), OPERATIONS[index][0].removeprefix('/api'))]
    for doc, path in docs:
        params = doc['paths'][path]['post'].get('parameters', [])
        params = [doc['components']['parameters'][p['$ref'].split('/')[-1]] if '$ref' in p else p for p in params]
        key = next(p for p in params if p['name'] == 'Idempotency-Key')
        assert key['required'] is True and key['schema']['minLength'] == 1 and key['schema']['maxLength'] == maximum


@pytest.mark.parametrize('accept,expected', [('', 406), ('application/json', 406), ('TEXT/EVENT-STREAM', 406),
                                          ('text/event-stream', 200), ('text/event-stream;q=0', 200)])
def test_stream_accept_and_failure_are_pre_stream_json(offline, accept, expected):
    resource, _ = pdf(offline)
    before = snapshot(offline)
    result = post(offline, 4, {'resource_id': resource['id']}, Accept=accept)
    assert result.status_code == expected
    if expected == 406:
        assert result.headers['content-type'].startswith('application/json')
        assert snapshot(offline) == before
        for check in validators(offline, OPERATIONS[4], error=True):
            check.validate(result.json())


@pytest.mark.parametrize('action,approved,decision', [
    ({'phase': 'context'}, False, 'allow'),
    ({'phase': 'tool_call', 'tool': 'unknown'}, False, 'deny'),
    ({'phase': 'context', 'content': '13812345678'}, False, 'deny'),
    ({'phase': 'provider_request'}, False, 'deny'),
    ({'phase': 'provider_request'}, True, 'allow'),
])
def test_guard_is_evaluation_only_and_does_not_echo_inputs(offline, action, approved, decision):
    body = {'action': action, 'policy': policy(provider_admitted=approved)}
    for check in validators(offline, OPERATIONS[3], request=True):
        check.validate(body)
        assert not check.is_valid({**body, 'extra': True})
    before_runtime = offline.get(OPERATIONS[0][0]).json()
    result = post(offline, 3, body)
    assert result.status_code == 200
    checks = valid(offline, OPERATIONS[3], result.json())
    assert result.json()['decision'] == decision
    assert ('13812345678' not in result.text)
    for check in checks:
        for field, value in [('model_calls', 1), ('external_calls', 1), ('phase', 'unknown'),
                             ('reasons', ['WRONG'] if decision == 'allow' else [])]:
            assert not check.is_valid({**result.json(), field: value}), field
    assert offline.get(OPERATIONS[0][0]).json() == before_runtime
    before = snapshot(offline)
    assert post(offline, 3, body).json() == result.json()
    assert snapshot(offline) == before


@pytest.mark.parametrize('operation', OPERATIONS)
def test_pi_error_envelopes_and_boundary_denial(offline, operation):
    result = offline.request(operation[1], operation[0], headers={'Origin': 'http://evil.example'})
    assert result.status_code == 403
    for check in validators(offline, operation, error=True):
        check.validate(result.json())
        assert not check.is_valid({'detail': []})
        bad = copy.deepcopy(result.json())
        bad['error']['retryable'] = True
        assert not check.is_valid(bad)


@pytest.mark.parametrize('state', ['default', 'missing', 'directory', 'invalid_json', 'invalid_utf8', 'null', 'approved'])
def test_runtime_admission_projection_not_execution(offline, tmp_path, monkeypatch, state):
    import backend.pi_admission as admission
    file = tmp_path / 'admission.json'
    original = json.loads(admission.ADMISSION_STATE.read_text())
    if state == 'directory':
        file.mkdir()
    elif state == 'invalid_json':
        file.write_text('{')
    elif state == 'invalid_utf8':
        file.write_bytes(b'\xff\xfe{')
    elif state == 'null':
        file.write_text('null')
    elif state == 'approved':
        original.update(status='approved_for_l3_probe', admission_enabled=True,
                        provider={'kind': 'pi_sidecar', 'package': 'fixture', 'authentication_boundary': 'managed_at_platform_transport_not_read_by_pi'},
                        model='fixture', budget={'currency': 'USD', 'max_cost_minor': 1, 'max_turns': 1, 'timeout_seconds': 1},
                        sources={'allowed_domains': ['example.com'], 'search': {'endpoint': 'http://example.com/search', 'credential_ref': None},
                                 'financial': {'endpoint': 'http://example.com/finance', 'credential_ref': None}},
                        public_pdf={'name': 'fixture.pdf', 'sha256': 'a' * 64, 'data_class': 'Public'},
                        operators={'cancel_owner': 'fixture', 'rollback_owner': 'fixture'}, blockers=[],
                        admission_evidence={k: 'fixture' for k in ['approval_record', 'data_egress_review', 'probe_runbook', 'rollback_runbook']})
        admission.validate(original)
        file.write_text(json.dumps(original))
    if state != 'default':
        monkeypatch.setattr(admission, 'ADMISSION_STATE', file)
    before = snapshot(offline)
    result = offline.get(OPERATIONS[0][0])
    assert result.status_code == 200, result.text
    value = result.json()
    checks = valid(offline, OPERATIONS[0], value)
    assert value['status'] == ('not_admitted' if state == 'default' else 'approved_for_l3_probe' if state == 'approved' else 'invalid_not_admitted')
    assert value['admission_enabled'] is (state == 'approved')
    assert value['blocker_count'] == len(value['blockers'])
    assert value['model_calls'] == value['external_calls'] == 0
    for check in checks:
        for field, altered in [('admission_enabled', not value['admission_enabled']), ('model_calls', 1), ('external_calls', -1)]:
            assert not check.is_valid({**value, field: altered}), field
    assert snapshot(offline) == before
