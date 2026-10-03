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
