import hashlib
import unittest
from course_compass.ingest import normalize, plain_text


class ExtractionTests(unittest.TestCase):
    def test_nested_alternatives_and_conditions_survive(self):
        html = '<ul><li>Complete all of:<ul><li>CSC225</li><li>Complete 1 of:<ul><li>MATH122 (minimum C)</li><li>ECE242</li></ul></li></ul></li></ul>'
        text = plain_text(html)
        self.assertIn('    • MATH122 (minimum C)', text)
        self.assertIn('  • Complete 1 of:', text)
        self.assertIn('• Complete all of:', text)

    def test_entities_inline_spacing_and_hidden_content(self):
        self.assertEqual(plain_text('<p>Complete <span>1</span> of A &amp; B</p><script>ignore</script>'),
                         'Complete 1 of A & B')

    def test_wrong_course_and_empty_description_are_rejected(self):
        course = {'__catalogCourseId': 'CSC225', '__passedCatalogQuery': True,
                  'subjectCode': {'name': 'CSC'}, 'pid': 'example', 'id': 'record',
                  'title': 'Example', 'description': '<p>Example</p>'}
        with self.assertRaises(ValueError):
            normalize(course, 'CSC226', {}, b'{}', 'now', 'url')
        course['description'] = '<p></p>'
        with self.assertRaises(ValueError):
            normalize(course, 'CSC225', {}, b'{}', 'now', 'url')

    def test_provenance_labels_and_original_html_are_preserved(self):
        html = '<p>Completed or concurrently enrolled in A</p>'
        course = {'__catalogCourseId': 'CSC225', '__passedCatalogQuery': True,
                  'subjectCode': {'name': 'CSC'}, 'pid': 'example', 'id': 'record',
                  'title': 'Example', 'description': '<p>Description</p>',
                  'preOrCorequisites': html}
        record = normalize(course, 'CSC225', {'preOrCorequisites': {'label': 'Pre- or corequisites'}},
                           b'{}', 'now', 'url')
        section = next(s for s in record['sections'] if s['field'] == 'preOrCorequisites')
        self.assertEqual(section['source_html'], html)
        self.assertEqual(section['label'], 'Pre- or corequisites')
        self.assertEqual(record['raw_sha256'], hashlib.sha256(b'{}').hexdigest())
        self.assertEqual(record['retrieved_at'], 'now')


if __name__ == '__main__':
    unittest.main()
