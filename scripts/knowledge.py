#!/usr/bin/env python3
"""Search, inspect and bind the bundled knowledge without Adobe or a network."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('knowledge_runtime', ROOT / 'runtime/darkroom/knowledge.py')
library = importlib.util.module_from_spec(spec)
spec.loader.exec_module(library)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=ROOT / 'knowledge')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('verify')
    search = sub.add_parser('search'); search.add_argument('query'); search.add_argument('--limit', type=int, default=12)
    show = sub.add_parser('show'); show.add_argument('identifier')
    template = sub.add_parser('template'); template.add_argument('identifier'); template.add_argument('--source-id', required=True); template.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest, catalog, index = library.load(args.library)
    if args.command == 'verify':
        result = {'verified': True, 'files': len(manifest['files']), 'counts': manifest['counts'], 'photographic_quality_verified': False}
    elif args.command == 'search':
        result = library.search(args.library, args.query, args.limit)
    elif args.command == 'show':
        docs = [d for d in index['documents'] if d['id'] == args.identifier]
        if docs:
            print(library.safe(args.library, docs[0]['path']).read_text()); return
        result = library.package(catalog, args.identifier)
    else:
        result = library.template(args.library, args.identifier, args.source_id)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2); handle.write('\n')
        result = {'template': str(args.output), 'ready_to_execute': False, 'instruction': 'Complete from actual observation, then prepare with --knowledge-plan.'}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
