"""Explicit loopback-only live probe; stores one synthetic package/execution audit.

Run on the deployed host or through an SSH local forward. Never runs the package
entrypoint in this host process. No model, external data, or credential access.
"""
import argparse
import io
import json
import sys
import urllib.parse
import urllib.request
import uuid
import zipfile


ENTRY = '''def main(payload):
    import os, socket
    sock = socket.socket(); sock.settimeout(0.5)
    try:
        sock.connect(('1.1.1.1', 443))
        denied = False
    except OSError:
        denied = True
    finally:
        sock.close()
    return {'sum': sum(payload['numbers']), 'uid': os.getuid(),
            'network_denied': denied,
            'host_visible': any(os.path.exists(p) for p in ['/opt/harnessagent', '/Users/weberzhao', '/root/.ssh']),
            'docker_socket_visible': os.path.exists('/var/run/docker.sock')}
'''


def probe(base):
    url = urllib.parse.urlsplit(base)
    if (url.scheme != 'http' or url.hostname != '127.0.0.1' or url.username or url.password
            or url.path not in {'', '/'} or url.query or url.fragment):
        raise ValueError('Probe requires a direct http://127.0.0.1:PORT endpoint')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = base.rstrip('/') + '/api/local/external-skills'

    def request(path, data=None, content_type='application/json'):
        headers = {'Content-Type': content_type, 'Idempotency-Key': 'ha0052-' + uuid.uuid4().hex}
        req = urllib.request.Request(base + path, data=data, headers=headers)
        with opener.open(req, timeout=40) as response:
            return json.load(response)

    status = request('/runtime')
    assert status['runtime_enabled'] and not status['blockers'], status
    manifest = dict(schema_version='external-skill-manifest@1', skill_id='ext_deployment_probe',
                    version='1.0.0', entrypoint='entry.py', runtime='python-stdlib@3.12',
                    capabilities=['transform_json'])
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('entry.py', ENTRY)
    package = request('/packages?source_label=HA-0052-synthetic-deployment-probe', raw.getvalue(), 'application/zip')
    result = request('/packages/' + package['id'] + ':execute',
                     json.dumps({'input': {'numbers': [2, 3, 5]}}).encode())
    assert result['output'] == dict(sum=10, uid=65532, network_denied=True,
                                   host_visible=False, docker_socket_visible=False), result
    assert result['audit']['container_cleaned'] is True
    return {'runtime': status, 'package_id': package['id'], 'execution_id': result['execution_id'],
            'checks': result['output'], 'audit': result['audit'], 'model_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    args = parser.parse_args()
    json.dump(probe(args.base_url), sys.stdout, indent=2)
    print()
