"""Single bounded local inference job, invoked with a minimal environment."""
import hashlib
import json
from pathlib import Path
import sys


def main():
    from fastembed import TextEmbedding
    root = Path(sys.argv[1])
    manifest = json.loads((root / 'support-model.json').read_text())
    if manifest.get('revision') != '46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59' or manifest.get('dimension') != 512:
        raise ValueError('invalid model manifest')
    names = {'config.json', 'model_optimized.onnx', 'special_tokens_map.json',
             'tokenizer.json', 'tokenizer_config.json', 'vocab.txt'}
    if set(manifest['files']) != names:
        raise ValueError('invalid model files')
    for name in names:
        if (root / name).is_symlink() or hashlib.sha256((root / name).read_bytes()).hexdigest() != manifest['files'][name]:
            raise ValueError('model changed')
    data = json.loads(sys.stdin.buffer.read(1000001))
    if (not isinstance(data, list) or not 1 <= len(data) <= 256
            or any(not isinstance(t, str) or len(t) > 8000 for t in data)):
        raise ValueError('invalid input')
    model = TextEmbedding('BAAI/bge-small-zh-v1.5', specific_model_path=str(root),
                          local_files_only=True, threads=2, cuda=False)
    vectors = [vector.tolist() for vector in model.embed(data, batch_size=16)]
    sys.stdout.write(json.dumps(vectors, allow_nan=False))


if __name__ == '__main__':
    main()
