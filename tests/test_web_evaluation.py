import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from course_compass.evaluation import load_frozen, run_holdout, sha, summarize_reviews, tfidf_search
from course_compass.server import make_handler
from course_compass.search import SearchIndex
from test_search_answers import course


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(SearchIndex([course()])))
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        status, mime, data = response.status, response.getheader('Content-Type'), response.read()
        connection.close()
        return status, mime, data

    def test_page_assets_and_configuration(self):
        for path in ['/', '/app.js', '/style.css']:
            status, _, data = self.request('GET', path)
            self.assertEqual(status, 200)
            self.assertTrue(data)
        with patch.dict(os.environ, {}, clear=True):
            _, _, data = self.request('GET', '/api/config')
            config = json.loads(data)
            self.assertFalse(config['model_ready'])
            self.assertNotIn('api_key', config)
            self.assertEqual(len(config['courses']), 1)

    def test_real_evidence_and_ambiguous_requests(self):
        for question, expected in [('CSC225 prerequisites', 'evidence'), ('Prerequisites for 225?', 'clarify')]:
            status, _, data = self.request('POST', '/api/ask', json.dumps({'question': question}), {'Content-Type': 'application/json'})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)['status'], expected)

    def test_invalid_input_origin_host_and_paths(self):
        for body in ['[]', '{}', '{bad', json.dumps({'question': ''}), json.dumps({'question': 'x', 'mode': 'invalid'})]:
            status, _, _ = self.request('POST', '/api/ask', body, {'Content-Type': 'application/json'})
            self.assertEqual(status, 400)
        status, _, _ = self.request('POST', '/api/ask', '{}', {'Content-Type': 'text/plain'})
        self.assertEqual(status, 415)
        status, _, _ = self.request('POST', '/api/ask', '{}', {'Content-Type': 'application/json', 'Origin': 'https://example.com'})
        self.assertEqual(status, 403)
        status, _, _ = self.request('GET', '/', headers={'Host': 'example.com'})
        self.assertEqual(status, 403)
        self.assertEqual(self.request('GET', '/../../.env')[0], 404)

    def test_model_error_is_clear_and_has_no_claims(self):
        with patch.dict(os.environ, {}, clear=True):
            status, _, data = self.request('POST', '/api/ask', json.dumps({'question': 'CSC225 prerequisites', 'mode': 'model'}), {'Content-Type': 'application/json'})
        self.assertEqual(status, 502)
        result = json.loads(data)
        self.assertEqual(result['claims'], [])
        self.assertIn('OPENAI_API_KEY', result['message'])


class SavedDemoTests(unittest.TestCase):
    def test_saved_examples_never_call_model(self):
        from course_compass.examples import EXAMPLES, saved_answer
        with patch('course_compass.answers.urlopen') as network:
            for example in EXAMPLES:
                result = saved_answer(example['question'])
                self.assertEqual(result['mode'], 'examples')
                self.assertEqual(result['status'], 'answer')
                self.assertIn('Not generated live', result['message'])
                self.assertIsNone(result['model'])
            self.assertEqual(saved_answer('An unrelated question')['status'], 'abstain')
            network.assert_not_called()

    def test_fresh_clone_server_without_imports(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(None))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            client.request('GET', '/api/config')
            config = json.loads(client.getresponse().read())
            self.assertFalse(config['corpus_ready'])
            self.assertEqual(len(config['examples']), 6)
            client.request('POST', '/api/ask', json.dumps({'question': config['examples'][0], 'mode': 'examples'}), {'Content-Type': 'application/json'})
            response = client.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['status'], 'answer')
            client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class EvaluationTests(unittest.TestCase):
    def make_dataset(self, root, index):
        path = root / 'holdout.json'
        questions = [{'id': f'test-{n}', 'question': 'CSC225 prerequisites', 'expected_behavior': 'answer',
                      'reference_answer': 'Both courses required.', 'supporting_section_ids': ['one:prerequisites']} for n in range(50)]
        path.write_text(json.dumps({'questions': questions}))
        path.with_suffix('.lock.json').write_text(json.dumps({'dataset_sha256': sha(path.read_bytes()),
            'corpus_sha256': sha(json.dumps(index.courses, sort_keys=True).encode()), 'frozen_at': 'test'}))
        return path

    def test_tfidf_ranking_and_empty_query(self):
        index = SearchIndex([course()])
        self.assertEqual(tfidf_search(index, 'CSC225 prerequisites')[0]['id'], 'one:prerequisites')
        self.assertEqual(tfidf_search(index, 'platypus'), [])

    def test_hash_lock_and_complete_offline_run(self):
        index = SearchIndex([course()])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.make_dataset(root, index)
            report = run_holdout(index, path, root / 'report.json')
            self.assertEqual(report['question_count'], 50)
            self.assertEqual(report['retrieval'][0]['all_evidence_hit_rate'], 1)
            self.assertIsNone(report['model_evaluation']['answer_accuracy'])
            self.assertFalse(report['model_evaluation']['executed'])
            path.write_text(path.read_text() + ' ')
            with self.assertRaises(ValueError):
                load_frozen(path)

    def test_model_preflight_and_corpus_mismatch(self):
        index = SearchIndex([course()])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.make_dataset(root, index)
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, 'OPENAI_API_KEY'):
                    run_holdout(index, path, root / 'report.json', model=True)
            index.courses[0]['title'] = 'Changed'
            with self.assertRaisesRegex(ValueError, 'Corpus differs'):
                run_holdout(index, path, root / 'report.json')

    def test_model_metrics_and_human_review_binding(self):
        index = SearchIndex([course()])
        response = {'status': 'answer', 'usage': {'input_tokens': 100, 'output_tokens': 10}, 'latency_ms': 20}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.make_dataset(root, index)
            report_path, review_path = root / 'report.json', root / 'reviews.json'
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test'}), patch('course_compass.evaluation.answer', return_value=response):
                report = run_holdout(index, path, report_path, model=True, input_price=1, output_price=2)
            self.assertAlmostEqual(report['model_evaluation']['estimated_cost_usd'], .006)
            review = {'dataset_sha256': report['dataset_sha256'], 'report_sha256': sha(report_path.read_bytes()),
                      'reviews': [{'id': r['id'], 'correct': True, 'citations_supported': True} for r in report['answers']]}
            review_path.write_text(json.dumps(review))
            self.assertEqual(summarize_reviews(report_path, review_path)['answerable_correctness'], 1)
            review['reviews'][0]['correct'] = None
            review_path.write_text(json.dumps(review))
            with self.assertRaises(ValueError):
                summarize_reviews(report_path, review_path)
            review['report_sha256'] = 'wrong'
            review_path.write_text(json.dumps(review))
            with self.assertRaises(ValueError):
                summarize_reviews(report_path, review_path)


if __name__ == '__main__':
    unittest.main()
