"""Command-line entry point for ingestion, retrieval, answers, and development checks."""
import argparse
import json
from pathlib import Path
import sys

from . import ingest
from .answers import answer
from .search import SearchIndex


def evaluate(index, questions_path, limit=8):
    questions = json.loads(questions_path.read_text())['questions']
    rows = []
    for case in questions:
        results = index.search(case['question'], limit)
        found = {d['id'] for d in results}
        expected = set(case['supporting_section_ids'])
        behavior = answer(index, case['question'])['status']
        rows.append({'id': case['id'], 'expected_sections': len(expected),
                     'retrieved_expected_sections': len(expected & found),
                     'all_evidence_found': expected <= found if expected else None,
                     'expected_behavior': case['expected_behavior'], 'offline_status': behavior})
    answerable = [r for r in rows if r['expected_sections']]
    return {'dataset': 'development only; not held-out answer accuracy', 'k': limit,
            'answerable_questions': len(answerable),
            'all_evidence_hit_rate': sum(r['all_evidence_found'] for r in answerable) / len(answerable) if answerable else None,
            'section_recall': sum(r['retrieved_expected_sections'] for r in answerable) / sum(r['expected_sections'] for r in answerable) if answerable else None,
            'cases': rows}


def render(result):
    lines = [f"Calendar: {result['calendar_edition']} | {result['status']} | {result['mode']}"]
    if result['message']:
        lines.append(result['message'])
    numbers = {c['id']: i for i, c in enumerate(result['citations'], 1)}
    for claim in result['claims']:
        markers = ' '.join(f"[{numbers[e['section_id']]}]" for e in claim['evidence'])
        lines.append(f"{claim['text']} {markers}")
    for citation in result['citations']:
        lines.extend([f"\n[{numbers[citation['id']]}] {citation['course_code']} — {citation['label']}",
                      citation['source_url'], citation['text']])
        if citation['quality_flags']:
            lines.append('Source note: ' + '; '.join(citation['quality_flags']))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('ingest')
    imp.add_argument('--offline', action='store_true')
    for name in ('search', 'ask'):
        p = sub.add_parser(name)
        p.add_argument('question')
        if name == 'search':
            p.add_argument('--limit', type=int, default=8)
        else:
            p.add_argument('--mode', choices=['evidence', 'model'], default='evidence')
            p.add_argument('--json', action='store_true')
    web = sub.add_parser('serve', help='Start the local student interface')
    web.add_argument('--port', type=int, default=8766)
    check = sub.add_parser('evaluate')
    check.add_argument('--output', type=Path)
    holdout = sub.add_parser('benchmark', help='Evaluate the frozen 50-question set')
    holdout.add_argument('--model', action='store_true', help='Make live model calls; requires credentials')
    holdout.add_argument('--output', type=Path, default=ingest.ROOT / 'evaluation' / 'holdout-report.json')
    holdout.add_argument('--input-price', type=float, help='USD per million input tokens')
    holdout.add_argument('--output-price', type=float, help='USD per million output tokens')
    template = sub.add_parser('review-template', help='Create a human scoring sheet for a model run')
    template.add_argument('report', type=Path)
    template.add_argument('--output', type=Path, required=True)
    review = sub.add_parser('review', help='Summarize a human-reviewed model run')
    review.add_argument('report', type=Path)
    review.add_argument('reviews', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'ingest':
            return ingest.run(ingest.ROOT / 'data', args.offline)
        if args.command == 'serve':
            from .server import serve
            serve(args.port)
            return 0
        if args.command == 'review-template':
            from .evaluation import review_template
            review_template(args.report, args.output)
            print(f'Review template: {args.output}')
            return 0
        if args.command == 'review':
            from .evaluation import summarize_reviews
            print(json.dumps(summarize_reviews(args.report, args.reviews), indent=2))
            return 0
        index = SearchIndex.load()
        if args.command == 'benchmark':
            from .evaluation import run_holdout
            report = run_holdout(index, ingest.ROOT / 'evaluation' / 'holdout.json', args.output,
                                 args.model, args.input_price, args.output_price)
            print(json.dumps({k: v for k, v in report.items() if k not in {'answers', 'implementation_sha256', 'retrieval'}}, indent=2))
            for method in report['retrieval']:
                print(f"{method['name']}: all-evidence hit rate={method['all_evidence_hit_rate']:.1%}, section recall={method['section_recall']:.1%}")
            print(f'Report: {args.output}')
            return 0
        if args.command == 'search':
            print(json.dumps(index.search(args.question, args.limit), indent=2, ensure_ascii=False))
        elif args.command == 'ask':
            result = answer(index, args.question, args.mode)
            print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result))
            return 1 if result['status'] == 'error' else 0
        else:
            report = evaluate(index, ingest.ROOT / 'evaluation' / 'development.json')
            if args.output:
                ingest.save_json(args.output, report)
            print(json.dumps(report, indent=2))
    except (OSError, ValueError, KeyError) as error:
        print(f'Course Compass: {error}', file=sys.stderr)
        return 1
    return 0
