import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from course_compass.answers import ModelError, answer, openai_generate, validate_answer
from course_compass.ingest import CATALOG_ID, EDITION
from course_compass.search import SearchIndex, codes


def course(code='CSC225', pid='one', text='Complete all of: CSC115 and MATH122.'):
    return {'course_code': code, 'title': 'Algorithms', 'catalog_id': CATALOG_ID,
            'calendar_edition': EDITION, 'source_url': 'https://www.uvic.ca/example',
            'quality_flags': [], 'sections': [
                {'id': pid + ':description', 'field': 'description', 'label': 'Description',
                 'text': 'Algorithms, sorting, graph traversal.'},
                {'id': pid + ':prerequisites', 'field': 'preAndCorequisites', 'label': 'Prerequisites', 'text': text}]}


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.index = SearchIndex([course(), course('CSC360', 'two', 'CSC225 and SENG265.')])

    def test_course_normalization_and_ambiguous_numbers(self):
        self.assertEqual(codes('csc 225 vs CSC-360'), ['CSC225', 'CSC360'])
        self.assertEqual(codes('prerequisites for 225'), [])
        self.assertEqual(answer(self.index, 'prerequisites for 225')['status'], 'clarify')

    def test_own_prerequisites_outrank_references(self):
        result = self.index.search('What are the prerequisites for CSC 225?')[0]
        self.assertEqual(result['id'], 'one:prerequisites')

    def test_empty_and_unmatched_queries(self):
        with self.assertRaises(ValueError):
            self.index.search(' ')
        self.assertEqual(self.index.search('platypus'), [])
        self.assertEqual(answer(self.index, 'platypus')['status'], 'abstain')

    def test_unsupported_and_live_information_skip_model(self):
        def fail(*args):
            self.fail('Model should not be called')
        for question in ['What does CSC 999 cover?', 'How many seats in CSC225?']:
            self.assertEqual(answer(self.index, question, 'model', fail)['status'], 'abstain')

    def test_wrong_edition_and_failed_manifest_rejected(self):
        wrong = course()
        wrong['calendar_edition'] = 'May 2025'
        with self.assertRaises(ValueError):
            SearchIndex([wrong])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'processed' / CATALOG_ID
            directory.mkdir(parents=True)
            (directory / 'manifest.json').write_text(json.dumps({'failures': ['failed']}))
            (directory / 'courses.json').write_text(json.dumps([course()]))
            with self.assertRaises(ValueError):
                SearchIndex.load(temporary)


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.index = SearchIndex([course()])
        self.evidence = self.index.search('CSC225 prerequisites')
        self.result = {'status': 'answer', 'message': '', 'claims': [
            {'text': 'Both listed courses are required.', 'evidence': [
                {'section_id': 'one:prerequisites', 'quote': 'Complete all of: CSC115 and MATH122.'}]}]}

    def test_valid_citations_and_mocked_pipeline(self):
        result = answer(self.index, 'What are CSC225 prerequisites?', 'model',
                        lambda q, e: (self.result, {'model': 'test', 'usage': {'input_tokens': 20}}))
        self.assertEqual(result['status'], 'answer')
        self.assertEqual(result['citations'][0]['source_url'], 'https://www.uvic.ca/example')
        self.assertEqual(result['usage']['input_tokens'], 20)

    def test_invented_id_and_quote_rejected(self):
        ref = self.result['claims'][0]['evidence'][0]
        ref['section_id'] = 'invented'
        with self.assertRaises(ModelError):
            validate_answer(self.result, self.evidence)
        ref['section_id'] = 'one:prerequisites'
        ref['quote'] = 'No prerequisites'
        with self.assertRaises(ModelError):
            validate_answer(self.result, self.evidence)

    def test_missing_citations_and_uncited_message_rejected(self):
        self.result['claims'][0]['evidence'] = []
        with self.assertRaises(ModelError):
            validate_answer(self.result, self.evidence)
        self.result['message'] = 'Uncited factual answer'
        with self.assertRaises(ModelError):
            validate_answer(self.result, self.evidence)

    def test_invalid_model_output_never_published(self):
        result = answer(self.index, 'CSC225 prerequisites', 'model',
                        lambda q, e: ({'status': 'answer'}, {}))
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['claims'], [])

    def test_no_key_has_actionable_error_and_no_network(self):
        with patch.dict(os.environ, {}, clear=True), patch('course_compass.answers.urlopen') as network:
            result = answer(self.index, 'CSC225 prerequisites', 'model')
            self.assertEqual(result['status'], 'error')
            self.assertIn('OPENAI_API_KEY', result['message'])
            network.assert_not_called()

    def test_request_contract_and_refusals_incomplete_responses(self):
        class Response:
            def __init__(self, body): self.body = body
            def __enter__(self):
                import io
                return io.StringIO(json.dumps(self.body))
            def __exit__(self, *args): pass
        body = {'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(self.result)}]}], 'usage': {}}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fake-test-key', 'OPENAI_MODEL': 'test-model'}):
            with patch('course_compass.answers.urlopen', return_value=Response(body)) as network:
                result, _ = openai_generate('question', self.evidence)
                self.assertEqual(result, self.result)
                payload = json.loads(network.call_args.args[0].data)
                self.assertFalse(payload['store'])
                self.assertEqual(payload['text']['format']['type'], 'json_schema')
                self.assertTrue(payload['text']['format']['strict'])
            for response in [{'status': 'incomplete'}, {'status': 'completed', 'output': [
                {'type': 'message', 'content': [{'type': 'refusal'}]}]}]:
                with patch('course_compass.answers.urlopen', return_value=Response(response)):
                    with self.assertRaises(ModelError):
                        openai_generate('question', self.evidence)
            for error in [HTTPError('url', 429, 'quota', {}, None), URLError('offline')]:
                with patch('course_compass.answers.urlopen', side_effect=error):
                    with self.assertRaises(ModelError):
                        openai_generate('question', self.evidence)
                if isinstance(error, HTTPError):
                    error.close()


if __name__ == '__main__':
    unittest.main()
