"""Explicit deployment-time download; runtime embedding never downloads models."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = 'Qdrant/bge-small-zh-v1.5'
REVISION = '46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59'
FILES = ['config.json', 'model_optimized.onnx', 'special_tokens_map.json',
         'tokenizer.json', 'tokenizer_config.json', 'vocab.txt']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    target = Path(parser.parse_args().directory).resolve()
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Deployment only. curl can use the operator's configured egress proxy;
    # no credentials or document text are supplied to these public downloads.
    for name in FILES:
        dest = target / name
        subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location',
            '--proto', '=https', '--max-time', '180', '--max-filesize', '200000000',
            f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}', '-o', str(dest)], check=True, timeout=185)
    manifest = {'model': 'BAAI/bge-small-zh-v1.5', 'dimension': 512, 'revision': REVISION,
                'files': {name: hashlib.sha256((target / name).read_bytes()).hexdigest() for name in FILES}}
    (target / 'support-model.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'ready': True, 'revision': REVISION, 'file_count': len(FILES)}))


if __name__ == '__main__':
    main()
