"""Inventory local course PDFs without copying their text or absolute paths."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess


def inventory(root: Path):
    rows = []
    for path in sorted(root.rglob('*.pdf')):
        if path.is_symlink():
            raise ValueError('Source inventory does not follow PDF symlinks')
        info = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, check=True).stdout
        pages = re.search(r'^Pages:\s+(\d+)', info, re.MULTILINE)
        if pages is None:
            raise ValueError('PDF page count missing')
        rows.append({'path': path.relative_to(root).as_posix(),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'pages': int(pages[1]), 'bytes': path.stat().st_size})
    groups = defaultdict(list)
    for row in rows:
        groups[row['sha256']].append(row['path'])
    return {'schema_version': 'course-source-inventory@1',
            'source_root_label': 'Downloads/jikesummary',
            'not_evidence': 'Inventory is not proof of reading, implementation, or acceptance.',
            'files': len(rows), 'unique_sha256': len(groups),
            'pages_including_duplicates': sum(r['pages'] for r in rows),
            'topics': dict(sorted(Counter(r['path'].split('/')[0] for r in rows).items())),
            'duplicate_groups': [v for v in groups.values() if len(v) > 1],
            'sources': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if not args.source.is_dir():
        parser.error('source must be an existing directory')
    result = inventory(args.source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('files', 'unique_sha256', 'pages_including_duplicates')}))
