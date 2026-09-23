from backend.app import create_app
from fastapi.testclient import TestClient


def pdf_fixture(text: str) -> bytes:
    stream = ('BT /F1 12 Tf 72 720 Td (' + text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ') Tj ET').encode()
    objects = [
        b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n',
        b'2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n',
        b'3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n',
        b'4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n',
        b'5 0 obj << /Length ' + str(len(stream)).encode() + b' >> stream\n' + stream + b'\nendstream endobj\n',
    ]
    result = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for obj in objects:
        offsets.append(len(result))
        result.extend(obj)
    xref = len(result)
    result.extend(b'xref\n0 6\n0000000000 65535 f \n')
    result.extend(b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:]))
    result.extend(b'trailer << /Size 6 /Root 1 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n')
    return bytes(result)


def test_pipeline_preview_is_structured_and_idempotent(tmp_path):
    app = create_app(tmp_path / 'pipeline.db', run_worker=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        uploaded = client.post(
            '/api/local/research-native/documents?name=contract.pdf',
            content=pdf_fixture('software development contract section 1 source code delivery and liability.'),
            headers={'content-type': 'application/pdf'},
        )
        assert uploaded.status_code == 201, uploaded.text
        body = {'resource_id': uploaded.json()['id'], 'chunk_max_chars': 1000}
        headers = {'Idempotency-Key': 'pipeline-preview-1'}
        response = client.post('/api/local/pi-contract-pipeline/preview', json=body, headers=headers)
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview['status'] == 'ready_for_skill'
        assert preview['classification']['contract_type'] == '技术服务'
        assert preview['classification']['method'] == 'deterministic_keyword_rules@1'
        assert preview['chunks'] and preview['security']['model_calls'] == 0
        replay = client.post('/api/local/pi-contract-pipeline/preview', json=body, headers=headers)
        assert replay.status_code == 200 and replay.json() == preview


def test_pipeline_security_hit_needs_human_without_leaking_raw_values(tmp_path):
    app = create_app(tmp_path / 'pipeline-security.db', run_worker=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        uploaded = client.post(
            '/api/local/research-native/documents?name=private-looking.pdf',
            content=pdf_fixture('采购合同 联系电话 13812345678，邮箱 foo@example.com'),
            headers={'content-type': 'application/pdf'},
        )
        response = client.post(
            '/api/local/pi-contract-pipeline/preview',
            json={'resource_id': uploaded.json()['id']},
            headers={'Idempotency-Key': 'pipeline-preview-security-1'},
        )
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'needs_human'
        assert {hit['kind'] for hit in result['security']['hits']} >= {'手机号', '邮箱'}
        assert '13812345678' not in response.text and 'foo@example.com' not in response.text


def test_pipeline_rejects_non_public_resource(tmp_path):
    app = create_app(tmp_path / 'pipeline-invalid.db', run_worker=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        uploaded = client.post('/api/v1/resources?name=input.csv', content=b'a,b\n1,2\n')
        response = client.post(
            '/api/local/pi-contract-pipeline/preview',
            json={'resource_id': uploaded.json()['id']},
            headers={'Idempotency-Key': 'pipeline-preview-invalid-1'},
        )
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'PDF_RESOURCE_INVALID'
