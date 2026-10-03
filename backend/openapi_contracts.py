"""Offline JSON Schema projection; rejects ambiguous component ownership."""
import json


def register_definitions(document, contract, namespace=''):
    """Copy definitions atomically; identical legacy shared definitions may coexist."""
    def project(value):
        if isinstance(value, list):
            return [project(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key == '$ref' and isinstance(item, str) and item.startswith('#/$defs/'):
                result[key] = '#/components/schemas/' + namespace + item[len('#/$defs/'):]
            else:
                result[key] = project(item)
        return result

    incoming = {namespace + name: project(value) for name, value in contract['$defs'].items()}
    existing = document.get('components', {}).get('schemas', {})
    for name, value in incoming.items():
        # JSON equality is strict about booleans versus integers (Python dict == is not).
        if name in existing and json.dumps(existing[name], sort_keys=True) != json.dumps(value, sort_keys=True):
            raise ValueError('OPENAPI_SCHEMA_COLLISION:' + name)
    document.setdefault('components', {}).setdefault('schemas', {}).update(incoming)


def assert_local_references(document):
    """No remote resolution or silently dangling JSON Pointer in the published doc."""
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == '$ref':
                    if not isinstance(item, str) or not item.startswith('#/'):
                        raise ValueError('OPENAPI_NONLOCAL_REFERENCE')
                    target = document
                    try:
                        for part in item[2:].split('/'):
                            key_part = part.replace('~1', '/').replace('~0', '~')
                            target = target[int(key_part)] if isinstance(target, list) else target[key_part]
                    except (KeyError, IndexError, ValueError, TypeError):
                        raise ValueError('OPENAPI_DANGLING_REFERENCE:' + item) from None
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(document)


def bind_chat_responses(document, domain, namespace):
    """Use the source contract for every existing chat route's success payload."""
    prefix = '/api/local/' + domain
    def response(path, method, status, definition):
        operation = document['paths'][prefix + path][method]
        operation['responses'][status]['content'] = {
            'application/json': {'schema': {'$ref': '#/components/schemas/' + namespace + definition}}}
    response('/runtime', 'get', '200', 'runtime_status')
    for path, entity, collection in (
        ('/providers', 'provider_profile', 'provider_list'),
        ('/models', 'model_profile', 'model_list'),
        ('/agents', 'agent_profile', 'agent_list'),
        ('/sessions', 'chat_session', 'session_list'),
    ):
        response(path, 'post', '201', entity)
        response(path, 'get', '200', collection)
    response('/sessions/{session_id}', 'get', '200', 'session_detail')
    if domain == 'agent-runtime':
        response('/providers/{provider_id}/readiness', 'get', '200', 'provider_readiness')


def bind_memory_research_reads(document):
    """Current local metadata reads; no runtime or admission side effects."""
    for path, method, status, definition in (
        ('/api/local/memory/runtime', 'get', '200', 'local_http_memory_runtime'),
        ('/api/local/memory/banks', 'get', '200', 'local_http_memory_bank_list'),
        ('/api/local/memory/banks', 'post', '201', 'memory_bank'),
        ('/api/local/memory/banks/{bank_id}', 'get', '200', 'local_http_memory_bank_detail'),
        ('/api/local/research', 'get', '200', 'local_http_research_demo_list'),
        ('/api/local/research-agents', 'get', '200', 'local_http_research_agents_list'),
        ('/api/local/research-native', 'get', '200', 'local_http_research_native_list'),
    ):
        operation = document['paths'][path][method]
        operation['responses'][status]['content'] = {
            'application/json': {'schema': {'$ref': '#/components/schemas/' + definition}}}
        envelope = {'description': 'Current local error envelope.', 'content': {
            'application/json': {'schema': {'$ref': '#/components/schemas/local_http_error'}}}}
        operation['responses']['default'] = envelope
        if '422' in operation['responses']:
            operation['responses']['422'] = envelope


def bind_pi_product_responses(document):
    """Offline Product Runs, not the separate no-Run PDF pipeline."""
    prefix = '/api/local/pi-contract-review'
    for suffix, method, status, response, request in (
        ('', 'post', '202', 'local_http_pi_created', 'request'),
        ('', 'get', '200', 'local_http_pi_list', None),
        ('/{run_id}', 'get', '200', 'local_http_pi_detail', None),
        ('/{run_id}/events', 'get', '200', 'local_http_pi_events', None),
        ('/{run_id}:gate', 'post', '200', 'local_http_pi_gate_result', 'gate_decision'),
    ):
        operation = document['paths'][prefix + suffix][method]
        operation['responses'][status]['content'] = {
            'application/json': {'schema': {'$ref': '#/components/schemas/' + response}}}
        envelope = {'description': 'Current local error envelope.', 'content': {
            'application/json': {'schema': {'$ref': '#/components/schemas/local_http_error'}}}}
        operation['responses']['default'] = envelope
        if '422' in operation['responses']:
            operation['responses']['422'] = envelope
        if request:
            operation['requestBody'] = {'required': True, 'content': {
                'application/json': {'schema': {'$ref': '#/components/schemas/pi_review_' + request}}}}
            operation.setdefault('parameters', []).append({
                'in': 'header', 'name': 'Idempotency-Key', 'required': True,
                'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128}})


def bind_memory_write_responses(document):
    """Current M1 historical receipts; no change to execution or deletion scope."""
    for path, method, status, definition in (
        ('/api/local/memory/banks/{bank_id}/retain', 'post', '201', 'local_http_memory_retained'),
        ('/api/local/memory/sources/{source_id}:retract', 'post', '200', 'local_http_memory_retracted'),
        ('/api/local/memory/sources/{source_id}', 'delete', '200', 'local_http_memory_deleted'),
    ):
        operation = document['paths'][path][method]
        operation['responses'][status]['content'] = {
            'application/json': {'schema': {'$ref': '#/components/schemas/' + definition}}}
        envelope = {'description': 'Current local error envelope.', 'content': {
            'application/json': {'schema': {'$ref': '#/components/schemas/local_http_error'}}}}
        operation['responses']['default'] = envelope
        if '422' in operation['responses']:
            operation['responses']['422'] = envelope
    document['paths']['/api/local/memory/sources/{source_id}:retract']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {
            'type': 'object', 'additionalProperties': False}}}}


def bind_pi_pipeline_responses(document):
    """Offline pipeline data, including one JSON envelope per SSE data frame."""
    prefix = '/api/local/pi-contract-pipeline/'
    for path, method, namespace, response, request, media in (
        ('/api/local/pi/runtime', 'get', 'pi_admission_', 'runtime_status', None, 'application/json'),
        (prefix + 'preview', 'post', 'pi_pipeline_', 'preview', 'http_request', 'application/json'),
        (prefix + 'review', 'post', 'pi_pipeline_', 'finding', 'http_request', 'application/json'),
        (prefix + 'security-check', 'post', 'pi_guard_', 'response', 'request', 'application/json'),
        (prefix + 'review-stream', 'post', 'pi_pipeline_', 'stream_event', 'http_request', 'text/event-stream'),
    ):
        operation = document['paths'][path][method]
        operation['responses']['200']['content'] = {
            media: {'schema': {'$ref': '#/components/schemas/' + namespace + response}}}
        envelope = {'description': 'Current local error envelope (before any SSE frames).', 'content': {
            'application/json': {'schema': {'$ref': '#/components/schemas/local_http_error'}}}}
        operation['responses']['default'] = envelope
        if '422' in operation['responses']:
            operation['responses']['422'] = envelope
        if request:
            operation['requestBody'] = {'required': True, 'content': {
                'application/json': {'schema': {'$ref': '#/components/schemas/' + namespace + request}}}}
            operation.setdefault('parameters', []).append({
                'in': 'header', 'name': 'Idempotency-Key', 'required': True,
                'schema': {'type': 'string', 'minLength': 1, 'maxLength': 120 if media == 'text/event-stream' else 128}})
        if media == 'text/event-stream':
            operation['parameters'].append({
                'in': 'header', 'name': 'Accept', 'required': True,
                'description': 'Current case-sensitive substring check, not full HTTP content negotiation.',
                'schema': {'type': 'string', 'pattern': 'text/event-stream'}})
            operation['responses']['200']['description'] = 'SSE data JSON frames: preview, finding, done; not model tokens or a passed Gate.'
            operation['responses']['200']['headers'] = {
                'Cache-Control': {'schema': {'const': 'no-store'}},
                'X-Accel-Buffering': {'schema': {'const': 'no'}}}


def bind_product_responses(document):
    """Publish current local Product wire contracts, not future API sketches."""
    contracts = (
        ('/api/v1/health', 'get', '200', 'local_http_health'),
        ('/api/v1/resources', 'get', '200', 'local_http_resource_list'),
        ('/api/v1/resources', 'post', '201', 'local_http_resource'),
        ('/api/v1/resources/{resource_id}', 'get', '200', 'local_http_resource'),
        ('/api/local/research-native/documents', 'post', '201', 'local_http_resource'),
        ('/api/local/tasks', 'post', '202', 'local_http_task_created'),
        ('/api/v1/tasks', 'post', '202', 'local_http_task_created'),
        ('/api/v1/tasks', 'get', '200', 'local_http_task_list'),
        ('/api/v1/tasks/{task_id}', 'get', '200', 'local_http_task_detail'),
        ('/api/v1/tasks/{task_id}/runs', 'post', '202', 'run'),
        ('/api/v1/runs/{run_id}', 'get', '200', 'run'),
        ('/api/v1/runs/{run_id}:cancel', 'post', '200', 'run'),
        ('/api/v1/runs/{run_id}/events', 'get', '200', 'local_http_event_page'),
        ('/api/v1/runs/{run_id}/artifacts', 'get', '200', 'local_http_artifact_list'),
        ('/api/v1/tasks/{task_id}/artifacts', 'get', '200', 'local_http_artifact_list'),
    )
    operations = []
    for path, method, status, definition in contracts:
        operation = document['paths'][path][method]
        operation['responses'][status]['content'] = {
            'application/json': {'schema': {'$ref': '#/components/schemas/' + definition}}}
        operations.append(operation)
    for path, media in (('/api/local/sample', 'text/csv'),
                        ('/api/v1/artifacts/{artifact_id}/content', '*/*')):
        operation = document['paths'][path]['get']
        operation['responses']['200']['content'] = {media: {'schema': {'type': 'string', 'format': 'binary'}}}
        operation['responses']['200']['headers'] = {'Content-Disposition': {'schema': {'type': 'string'}}}
        operations.append(operation)
    for operation in operations:
        envelope = {'description': 'Current local error envelope.', 'content': {
            'application/json': {'schema': {'$ref': '#/components/schemas/local_http_error'}}}}
        operation['responses']['default'] = envelope
        if '422' in operation['responses']:
            operation['responses']['422'] = envelope
    document['paths']['/api/v1/tasks/{task_id}/runs']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {
            'schema': {'$ref': '#/components/schemas/local_http_rerun_request'}}}}
    for path, media in (('/api/v1/resources', '*/*'),
                        ('/api/local/research-native/documents', 'application/pdf')):
        document['paths'][path]['post']['requestBody'] = {
            'required': True, 'content': {media: {'schema': {'type': 'string', 'format': 'binary'}}}}
