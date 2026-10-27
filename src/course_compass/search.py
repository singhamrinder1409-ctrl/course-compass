"""Section-level BM25 retrieval with course identifiers and field-aware ranking."""
from collections import Counter
import json
import math
from pathlib import Path
import re

from .ingest import CATALOG_ID, EDITION, ROOT

CODE = re.compile(r'\b(CSC|SENG|MATH|ECE|ENGR|STAT|PSYC|GEOG|ATWP|ENSH)\s*-?\s*(\d{3}[A-Za-z]?)\b', re.I)
STOP = set('a an the is are does do what which how can i for of in to and or with both either me my it'.split())


def codes(text):
    return [m.group(1).upper() + m.group(2).upper() for m in CODE.finditer(text)]


def tokens(text):
    text = CODE.sub(lambda m: m.group(1) + m.group(2), text.lower())
    return [t for t in re.findall(r'[a-z0-9]+', text) if t not in STOP]


def fields(question):
    q = question.lower()
    if re.search(r'prerequis|corequis|concurrent|require|complete before', q):
        return {'preAndCorequisites', 'preOrCorequisites'}
    if re.search(r'credit.*both|credit.*only|exclusion', q):
        return {'supplementalNotes'}
    if re.search(r'topic|cover|description|learn|teach|compare|differ', q):
        return {'description'}
    return set()


class SearchIndex:
    def __init__(self, courses):
        if not courses:
            raise ValueError('Corpus is empty; run the importer first.')
        self.courses = courses
        self.documents = []
        seen = set()
        for course in courses:
            if course['catalog_id'] != CATALOG_ID or course['calendar_edition'] != EDITION:
                raise ValueError('Corpus mixes or uses an unsupported calendar edition.')
            for section in course['sections']:
                if section['id'] in seen:
                    raise ValueError('Duplicate section identifier.')
                seen.add(section['id'])
                self.documents.append({
                    **{k: course[k] for k in ('course_code', 'title', 'calendar_edition', 'source_url', 'quality_flags')},
                    **{k: section[k] for k in ('id', 'field', 'label', 'text')},
                })
        self.counts = [Counter(tokens(' '.join(d[k] for k in ('course_code', 'title', 'label', 'text'))))
                       for d in self.documents]
        self.average_length = sum(sum(c.values()) for c in self.counts) / len(self.counts)
        self.df = Counter(t for counts in self.counts for t in counts)

    @classmethod
    def load(cls, data_dir=ROOT / 'data'):
        directory = Path(data_dir) / 'processed' / CATALOG_ID
        manifest = json.loads((directory / 'manifest.json').read_text())
        corpus = json.loads((directory / 'courses.json').read_text())
        if manifest.get('failures') or manifest.get('courses') != corpus:
            raise ValueError('Latest import failed or corpus does not match its manifest. Re-import first.')
        return cls(corpus)

    def search(self, question, limit=6):
        if not isinstance(question, str) or not question.strip() or len(question) > 4000:
            raise ValueError('Question must contain 1–4000 characters.')
        if not 1 <= limit <= 20:
            raise ValueError('Search limit must be between 1 and 20.')
        query = set(tokens(question))
        mentioned = set(codes(question))
        preferred = fields(question)
        ranked = []
        for document, counts in zip(self.documents, self.counts):
            score = 0.0
            length = sum(counts.values())
            for term in query:
                frequency = counts[term]
                if frequency:
                    idf = math.log(1 + (len(self.documents) - self.df[term] + .5) / (self.df[term] + .5))
                    score += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / self.average_length))
            if score <= 0:
                continue
            # Course references in prerequisites must not outrank the requested course.
            if document['course_code'] in mentioned:
                score += 5
                if document['field'] in preferred:
                    score += 5
            ranked.append({**document, 'score': round(score, 6)})
        return sorted(ranked, key=lambda d: (-d['score'], d['id']))[:limit]
