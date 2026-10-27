"""Authored demo answers, never presented as recorded model outputs."""
from copy import deepcopy

from .ingest import EDITION, LANDING

EXAMPLES = []


def example(question, code, pid, label, answer_text, note):
    section_id = 'example:' + code
    EXAMPLES.append({'question': question, 'calendar_edition': EDITION, 'mode': 'examples',
        'status': 'answer', 'message': 'Saved example, authored for this demo. Not generated live. Source notes below are paraphrases, not quotations.',
        'claims': [{'text': answer_text, 'evidence': [{'section_id': section_id, 'quote': ''}]}],
        'citations': [{'id': section_id, 'course_code': code, 'label': label + ' · paraphrased note',
            'source_url': LANDING + '#/courses/' + pid, 'text': note, 'quality_flags': []}],
        'model': None, 'usage': {}, 'latency_ms': 0})


example('What are the prerequisites for CSC 360?', 'CSC360', 'SkWiJ_6mE', 'Prerequisites',
        'CSC 360 requires CSC 225 and SENG 265, plus one of CSC 120 or ENGR 130, and one of CSC 230 or ECE 255. Meeting these published groups does not guarantee registration eligibility.',
        'The source organizes the requirements into required courses and two separate alternative groups. All groups matter.')
example('What topics does CSC 225 cover?', 'CSC225', 'Bk_cy_a7V', 'Course description',
        'CSC 225 introduces algorithm analysis, searching and sorting, data structures, and fundamental graph algorithms.',
        'The description discusses complexity, correctness, trees, heaps, and graph traversal among its foundational topics.')
example('Can I take STAT 260 concurrently with CSC 226?', 'CSC226', 'HytcJuaQV', 'Pre- or corequisites',
        'Yes. STAT 260 is one of the listed pre- or corequisite alternatives for CSC 226. CSC 225 is a separate prerequisite; the alternatives are not a substitute for it.',
        'The calendar separates the prior-course requirement from a group that permits prior completion or concurrent enrollment.')
example('Does CSC 110 introduce software testing?', 'CSC110', 'rkgWq1OpQE', 'Course description',
        'Yes. The introductory programming description includes testing alongside program design, control flow, collections, objects, and classes.',
        'Testing appears as an introductory topic in the published description.')
example('Does CSC 115 include recursion?', 'CSC115', 'Hkm5kuT7V', 'Course description',
        'Yes. Recursion is included in the description. The source also contains apparent editorial wording, so consult the official page for the current text.',
        'The saved September 2026 description includes recursion and an editorial instruction that the importer flags rather than removing.')
example('Does CSC 320 cover Turing machines?', 'CSC320', 'rJTqk_aXN', 'Course description',
        'Yes. Turing machines are listed among typical topics in CSC 320, together with formal models, languages, and computational complexity.',
        'These are typical topics from the description, not a guarantee of a particular instructor’s weekly syllabus.')


def saved_answer(question):
    if not isinstance(question, str) or not question.strip() or len(question) > 4000:
        raise ValueError('Question must contain 1–4000 characters.')
    key = ' '.join(question.lower().split()).rstrip('? .')
    for record in EXAMPLES:
        if ' '.join(record['question'].lower().split()).rstrip('? .') == key:
            return deepcopy(record)
    return {'question': question, 'calendar_edition': EDITION, 'mode': 'examples', 'status': 'abstain',
            'message': 'No saved example matches this question. Choose an example button, or import the course data and switch to Source excerpts for live search.',
            'claims': [], 'citations': [], 'model': None, 'usage': {}, 'latency_ms': 0}
