"""Frozen-set retrieval comparison, optional model run, and explicit human review."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time

from .answers import answer
from .ingest import ROOT, save_json
from .search import tokens


def tfidf_search(index, question, limit=8):
    """Sparse lexical vectors; not semantic embeddings. No course/field boosts."""
    def vector(counts):
        return {term: (1 + math.log(n)) * (1 + math.log((len(index.documents) + 1) / (index.df[term] + 1)))
                for term, n in counts.items() if term in index.df}
    query = vector(Counter(tokens(question)))
    qnorm = math.sqrt(sum(v * v for v in query.values()))
    rows = []
    for doc, counts in zip(index.documents, index.counts):
        v = vector(counts)
        norm = math.sqrt(sum(weight * weight for weight in v.values()))
        score = sum(weight * v.get(term, 0) for term, weight in query.items()) / (norm * qnorm) if norm and qnorm else 0
        if score > 0:
            rows.append({**doc, 'score': score})
    return sorted(rows, key=lambda d: (-d['score'], d['id']))[:limit]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def load_frozen(path):
    lock = json.loads(path.with_suffix('.lock.json').read_text())
    data = path.read_bytes()
    if sha(data) != lock['dataset_sha256']:
        raise ValueError('Frozen dataset hash mismatch. Do not silently replace the test set.')
    dataset = json.loads(data)
    ids = [q['id'] for q in dataset['questions']]
    if len(ids) != 50 or len(set(ids)) != 50:
        raise ValueError('Expected 50 uniquely identified questions.')
    return dataset, lock


def run_holdout(index, dataset_path, output, model=False, input_price=None, output_price=None):
    dataset, lock = load_frozen(dataset_path)
    corpus_hash = sha(json.dumps(index.courses, sort_keys=True).encode())
    if corpus_hash != lock['corpus_sha256']:
        raise ValueError('Corpus differs from the frozen evaluation snapshot.')
    questions = dataset['questions']
    available = {d['id'] for d in index.documents}
    if any(not set(q['supporting_section_ids']) <= available for q in questions):
        raise ValueError('Evaluation contains unknown supporting sections.')
    if model and not (os.environ.get('OPENAI_API_KEY', '').strip() and os.environ.get('OPENAI_MODEL', '').strip()):
        raise ValueError('Model evaluation needs OPENAI_API_KEY and OPENAI_MODEL. Run without --model for retrieval only.')
    if (input_price is None) != (output_price is None):
        raise ValueError('Provide both input and output prices per million tokens.')
    if any(p is not None and (not math.isfinite(p) or p < 0) for p in (input_price, output_price)):
        raise ValueError('Token prices must be finite nonnegative numbers.')
    report = {'dataset_sha256': lock['dataset_sha256'], 'corpus_sha256': corpus_hash,
              'frozen_at': lock['frozen_at'], 'run_at': datetime.now(timezone.utc).isoformat(),
              'question_count': len(questions), 'answerable_count': sum(q['expected_behavior'] == 'answer' for q in questions),
              'k': 8, 'retrieval': [], 'behavior': {}, 'model_evaluation': {}}
    for name, search in [('BM25 + course/field boosts', index.search),
                         ('TF-IDF cosine (lexical vectors)', lambda q, k: tfidf_search(index, q, k))]:
        rows = []
        for case in questions:
            start = time.perf_counter()
            results = search(case['question'], report['k'])
            elapsed = (time.perf_counter() - start) * 1000
            expected = set(case['supporting_section_ids'])
            ids = [r['id'] for r in results]
            ranks = [ids.index(s) + 1 for s in expected if s in ids]
            rows.append({'id': case['id'], 'retrieved_ids': ids,
                         'expected_count': len(expected), 'found_count': len(ranks),
                         'all_evidence_found': len(ranks) == len(expected) if expected else None,
                         'reciprocal_rank': 1 / min(ranks) if ranks else 0,
                         'latency_ms': round(elapsed, 4)})
        positive = [r for r in rows if r['expected_count']]
        latencies = [r['latency_ms'] for r in rows]
        report['retrieval'].append({'name': name,
            'all_evidence_hit_rate': statistics.mean(r['all_evidence_found'] for r in positive),
            'section_recall': sum(r['found_count'] for r in positive) / sum(r['expected_count'] for r in positive),
            'mean_reciprocal_rank': statistics.mean(r['reciprocal_rank'] for r in positive),
            'latency_p50_ms': statistics.median(latencies), 'latency_p95_ms': percentile(latencies, .95), 'cases': rows})
    results = []
    for case in questions:
        response = answer(index, case['question'], 'model' if model else 'evidence')
        results.append({'id': case['id'], 'expected_behavior': case['expected_behavior'],
                        'reference_answer': case['reference_answer'], 'result': response,
                        'review': {'correct': None, 'citations_supported': None, 'notes': ''}})
    for expected in ('abstain', 'clarify'):
        subset = [r for r in results if r['expected_behavior'] == expected]
        report['behavior'][expected] = {'count': len(subset), 'correct_status': sum(r['result']['status'] == expected for r in subset),
                                        'rate': sum(r['result']['status'] == expected for r in subset) / len(subset) if subset else None}
    report['model_evaluation'] = {
        'executed': model, 'answer_accuracy': None, 'citation_support': None,
        'errors': sum(r['result']['status'] == 'error' for r in results),
        'note': 'Model answers generated; human correctness and citation review is pending.' if model else 'AI answer accuracy, citation support, token cost, and model latency are unmeasured: no model calls were made.'}
    if model:
        uses = [r['result']['usage'] for r in results]
        in_tokens = sum(u.get('input_tokens', 0) for u in uses)
        out_tokens = sum(u.get('output_tokens', 0) for u in uses)
        prices = {'input_usd_per_million': input_price, 'output_usd_per_million': output_price}
        # Cached-input discounts are not modeled; this is an explicit estimate.
        report['model_evaluation'].update({'model': os.environ['OPENAI_MODEL'], 'input_tokens': in_tokens, 'output_tokens': out_tokens,
            'estimated_cost_usd': (in_tokens * input_price + out_tokens * output_price) / 1e6 if input_price is not None else None,
            'price_assumptions': prices, 'latency_p50_ms': statistics.median(r['result']['latency_ms'] for r in results),
            'latency_p95_ms': percentile([r['result']['latency_ms'] for r in results], .95)})
    report['answers'] = results
    report['implementation_sha256'] = {p.name: sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')}
    save_json(output, report)
    return report


def summarize_reviews(report_path, review_path):
    """A separate review file prevents grading from changing run evidence."""
    report = json.loads(report_path.read_text())
    review = json.loads(review_path.read_text())
    if not report['model_evaluation']['executed']:
        raise ValueError('Evidence-only runs cannot be graded as generated answers.')
    if review.get('dataset_sha256') != report['dataset_sha256']:
        raise ValueError('Reviews refer to a different test set.')
    if review.get('report_sha256') != sha(report_path.read_bytes()):
        raise ValueError('Reviews refer to a different model run.')
    by_id = {r['id']: r for r in review['reviews']}
    if len(by_id) != len(review['reviews']) or set(by_id) != {r['id'] for r in report['answers']}:
        raise ValueError('Review every case exactly once.')
    for row in by_id.values():
        if type(row.get('correct')) is not bool or type(row.get('citations_supported')) not in (bool, type(None)):
            raise ValueError('Each correctness score must be true/false; citation support true/false or null.')
    answerable = [r for r in report['answers'] if r['expected_behavior'] == 'answer']
    generated = [r for r in report['answers'] if r['result']['status'] == 'answer']
    if any(type(by_id[r['id']]['citations_supported']) is not bool for r in generated):
        raise ValueError('Every generated answer needs a citation-support review.')
    return {'dataset_sha256': report['dataset_sha256'],
            'reviewed_cases': len(by_id),
            'overall_behavior_and_correctness': statistics.mean(r['correct'] for r in by_id.values()),
            'answerable_correctness': statistics.mean(by_id[r['id']]['correct'] and r['result']['status'] == 'answer' for r in answerable),
            'citation_support_among_generated_answers': statistics.mean(by_id[r['id']]['citations_supported'] for r in generated) if generated else None}


def review_template(report_path, output):
    report = json.loads(report_path.read_text())
    if not report['model_evaluation']['executed']:
        raise ValueError('Generate a model run before creating an answer-review template.')
    save_json(output, {'dataset_sha256': report['dataset_sha256'], 'report_sha256': sha(report_path.read_bytes()),
        'rubric': 'Correct means fully answers the question with all conditions preserved, or correctly abstains/clarifies. Errors on answerable cases are false. Citation support means every generated factual claim is entailed by its cited passages, not merely that quotations exist. Use null only when no answer was generated.',
        'reviews': [{'id': r['id'], 'question': r['result'].get('question'),
                     'reference_answer': r['reference_answer'],
                     'correct': None, 'citations_supported': None, 'notes': ''} for r in report['answers']]})
