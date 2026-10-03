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
    cursor = document['paths']['/api/v1/runs/{run_id}/events']['get']
    for parameter in cursor['parameters']:
        if parameter['name'] == 'after':
            parameter['schema']['minimum'] = 0
