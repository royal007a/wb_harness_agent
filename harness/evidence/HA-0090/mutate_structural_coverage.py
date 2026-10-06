"""Process-local targeted mutations; never rewrite production files."""
import argparse
import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mutation', choices=('parent', 'path', 'plan_binding', 'verify_binding'))
    parser.add_argument('--xml', required=True)
    args = parser.parse_args()
    if args.mutation in ('parent', 'path'):
        module = importlib.import_module('backend.dsh_findings')
        old, new = {
            'parent': ("item.get('parent_id') in payment_parents", 'False'),
            'path': ("any(PAYMENT_LEXICON.search(title) for title in item.get('structural_path', []))", 'False'),
        }[args.mutation]
        selection = 'not sdk'
    else:
        module = importlib.import_module('backend.dsh_runtime')
        old, new = {
            'plan_binding': ('finding_candidates(clauses, clause_context)', 'finding_candidates(clauses)'),
            'verify_binding': ('verify_findings(args, clauses, seen_clauses, chunk_context=clause_context)',
                               'verify_findings(args, clauses, seen_clauses)'),
        }[args.mutation]
        selection = 'sdk'
    source = Path(module.__file__).read_text()
    assert source.count(old) == 1, 'mutation anchor must be unique'
    exec(compile(source.replace(old, new), module.__file__, 'exec'), module.__dict__)
    import pytest
    raise SystemExit(pytest.main(['-q', str(ROOT / 'tests/test_chinese_clause_coverage.py'),
                                 '-k', selection, '--junitxml=' + args.xml]))


if __name__ == '__main__':
    main()
