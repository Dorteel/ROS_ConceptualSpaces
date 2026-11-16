"""WordNet exploration and versioned, recoverable gradient persistence."""
import copy
import hashlib
import json
import math
import os
import random
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import fcntl

SCHEMA_VERSION = 1
SETUP = (
    'WordNet is unavailable. From the repository root, run:\n'
    'python3 -m venv .venv\n'
    '.venv/bin/python -m pip install -r tools/semantic_gradient/requirements.txt\n'
    '.venv/bin/python -m nltk.downloader wordnet\n'
    'Then restart ./semantic-gradient.sh. No system-wide pip installation is needed.'
)


class ResourceUnavailable(Exception):
    pass


class Conflict(Exception):
    pass


def endpoint(lemma):
    return {'word': lemma.name().replace('_', ' '), 'synset': lemma.synset().name(),
            'lemma': lemma.name(), 'lemma_key': lemma.key()}


def pair_id(endpoints):
    identities = sorted((e['synset'], e['lemma_key']) for e in endpoints.values())
    return hashlib.sha256(json.dumps(identities).encode()).hexdigest()[:20]


def new_document(endpoints):
    return {'schema_version': SCHEMA_VERSION, 'id': pair_id(endpoints),
            'antonyms': {side: value['word'] for side, value in endpoints.items()},
            'endpoints': endpoints, 'gradient': [], 'created_at': None, 'modified_at': None}


class WordNetService:
    def __init__(self, corpus=None, rng=None):
        self.corpus = corpus
        self.rng = rng or random.Random()
        self._pairs = None

    def load(self):
        try:
            if self.corpus is None:
                from nltk.corpus import wordnet
                self.corpus = wordnet
            self.corpus.ensure_loaded()
            return self.corpus
        except (ImportError, LookupError) as exc:
            raise ResourceUnavailable(SETUP) from exc

    def pairs(self):
        if self._pairs is not None:
            return self._pairs
        corpus = self.load()
        found = {}
        for synset in corpus.all_synsets():
            for lemma in synset.lemmas():
                for opposite in lemma.antonyms():
                    ends = sorted([endpoint(lemma), endpoint(opposite)], key=lambda e: (e['word'], e['lemma_key']))
                    if ends[0]['word'].casefold() == ends[1]['word'].casefold():
                        continue
                    if not all(re.fullmatch(r"[A-Za-z][A-Za-z ' -]*", e['word']) for e in ends):
                        continue
                    document = new_document(dict(zip(('left', 'right'), ends)))
                    # Prefer attested, short adjective pairs, while retaining other POS.
                    score = (1 + min(lemma.count() + opposite.count(), 30)) ** 2
                    score *= 3 if synset.pos() in ('a', 's') else 1
                    score /= 1 + sum(e['word'].count(' ') for e in ends)
                    found.setdefault(document['id'], (document, score))
        self._pairs = list(found.values())
        return self._pairs

    def lookup(self, word):
        """Find exact lexical labels in the shared, sense-preserving antonym index."""
        if not isinstance(word, str) or not word.strip() or len(word) > 120:
            raise ValueError('Enter a word or short phrase of 1–120 characters.')
        normalized = ' '.join(word.replace('_', ' ').split()).casefold()
        corpus = self.load()
        matches = []
        for document, _ in self.pairs():
            if normalized not in {e['word'].casefold() for e in document['endpoints'].values()}:
                continue
            matches.append({
                'document': copy.deepcopy(document),
                'senses': {side: corpus.synset(ep['synset']).definition()
                           for side, ep in document['endpoints'].items()},
            })
        return sorted(matches, key=lambda m: (tuple(m['document']['antonyms'].values()),
                                              m['document']['id']))

    def sample(self, count=5, exclude=(), retain=()):
        if type(count) is not int or not 1 <= count <= 50:
            raise ValueError('Pair count must be an integer between 1 and 50.')
        retained = set(retain)
        pairs = [p for p in self.pairs() if p[0]['id'] not in retained]
        excluded = set(exclude)
        fresh = [p for p in pairs if p[0]['id'] not in excluded]
        pool = fresh if len(fresh) >= count else pairs
        # Weighted sampling without replacement; also deduplicate visible lexical labels.
        ranked = sorted(pool, key=lambda p: self.rng.random() ** (1 / p[1]), reverse=True)
        result, labels = [], set()
        for document, _ in ranked:
            label = tuple(sorted(v.casefold() for v in document['antonyms'].values()))
            if label not in labels:
                result.append(copy.deepcopy(document))
                labels.add(label)
            if len(result) == count:
                break
        return result

    def suggestions(self, endpoints):
        corpus = self.load()
        excluded = {e['word'].casefold() for e in endpoints.values()}
        candidates = {}
        for side, ep in endpoints.items():
            synset = corpus.synset(ep['synset'])
            if not any(l.key() == ep['lemma_key'] for l in synset.lemmas()):
                raise ValueError('Endpoint lemma does not belong to its WordNet synset.')
            related = [('synonym', synset)]
            if synset.pos() in ('a', 's'):
                related += [('similar_to', s) for s in synset.similar_tos()]
                related += [('also_see', s) for s in synset.also_sees()]
            for relation, target in related:
                for lemma in target.lemmas():
                    word = lemma.name().replace('_', ' ')
                    if word.casefold() in excluded:
                        continue
                    provenance = {'endpoint': side, 'from_synset': synset.name(),
                                  'relation': relation, 'synset': target.name(),
                                  'lemma': lemma.name(), 'lemma_key': lemma.key()}
                    item = candidates.setdefault(word.casefold(), {'concept': word, 'provenance': []})
                    if provenance not in item['provenance']:
                        item['provenance'].append(provenance)
        return sorted(candidates.values(), key=lambda item: item['concept'])[:60]


def validate(document):
    if not isinstance(document, dict) or document.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported gradient schema.')
    if document.get('axis_origin', 'random') not in ('random', 'manual'):
        raise ValueError('Unknown axis origin.')
    ends = document.get('endpoints')
    if not isinstance(ends, dict) or set(ends) != {'left', 'right'}:
        raise ValueError('Two endpoints are required.')
    for ep in ends.values():
        if not isinstance(ep, dict) or any(not isinstance(ep.get(k), str) or not ep[k].strip()
                                          or len(ep[k]) > 300 for k in ('word', 'synset', 'lemma', 'lemma_key')):
            raise ValueError('Each endpoint needs a word, synset, lemma, and lemma key.')
    if document.get('id') != pair_id(ends):
        raise ValueError('Gradient identifier does not match its endpoints.')
    if document.get('antonyms') != {s: ep['word'] for s, ep in ends.items()}:
        raise ValueError('Endpoint labels do not match.')
    gradient = document.get('gradient')
    if not isinstance(gradient, list) or len(gradient) > 500:
        raise ValueError('Expected at most 500 concepts.')
    for item in gradient:
        if not isinstance(item, dict):
            raise ValueError('Invalid concept.')
        word, pos = item.get('concept'), item.get('position')
        if not isinstance(word, str) or not word.strip() or len(word) > 120:
            raise ValueError('Concepts must contain 1–120 characters.')
        if type(pos) not in (int, float) or not math.isfinite(pos) or not 0 < pos < 1:
            raise ValueError('Intermediate positions must be strictly between 0 and 1.')
        if item.get('source') not in ('manual', 'wordnet'):
            raise ValueError('Unknown concept source.')
        if item['source'] == 'wordnet':
            provenance = item.get('provenance')
            if not isinstance(provenance, list) or not provenance:
                raise ValueError('WordNet concepts require provenance.')
            for p in provenance:
                if (not isinstance(p, dict) or p.get('endpoint') not in ends
                    or p.get('relation') not in ('synonym', 'similar_to', 'also_see')
                    or any(not isinstance(p.get(k), str) or not p[k] for k in
                           ('from_synset', 'synset', 'lemma', 'lemma_key'))):
                    raise ValueError('Invalid WordNet provenance.')


def markdown(document):
    def escape(value):
        return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')
    ends = document['endpoints']
    rows = [f"# {escape(ends['left']['word'])} — {escape(ends['right']['word'])}", '',
            f"Schema: {document['schema_version']} · ID: {document['id']}", '',
            f"Created: {document['created_at']}", f"Modified: {document['modified_at']}", '',
            'Positions are human judgments; WordNet supplies lexical candidates only.', '',
            '| Position | Concept | Source | Provenance |', '| --- | --- | --- | --- |']
    entries = [(0, ends['left']['word'], 'endpoint', ends['left']),
               (1, ends['right']['word'], 'endpoint', ends['right'])]
    entries.extend((i['position'], i['concept'], i['source'],
                    i.get('provenance', i.get('origin', []))) for i in document['gradient'])
    for position, word, source, provenance in sorted(entries, key=lambda entry: entry[0]):
        detail = json.dumps(provenance, ensure_ascii=False)
        rows.append(f"| {position:.6g} | {escape(word)} | {source} | {escape(detail)} |")
    return '\n'.join(rows) + '\n'


def atomic_write(path, text):
    fd, temporary = tempfile.mkstemp(prefix='.gradient-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class GradientStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        # JSON is the commit point. Repair mirrors after interrupted writes.
        with self.lock():
            for path in self.directory.glob('*.json'):
                doc = json.loads(path.read_text(encoding='utf-8'))
                validate(doc)
                mirror = path.with_suffix('.md')
                expected = markdown(doc)
                if not mirror.exists() or mirror.read_text(encoding='utf-8') != expected:
                    atomic_write(mirror, expected)

    @contextmanager
    def lock(self):
        with (self.directory / '.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def path_for(self, document):
        labels = '-'.join(document['antonyms'][s] for s in ('left', 'right'))
        slug = re.sub(r'[^a-z0-9]+', '-', labels.lower()).strip('-')[:80] or 'gradient'
        # Always include sense identity: filenames never depend on save order.
        return self.directory / f"{slug}--{document['id']}.json"

    def load(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{20}', identifier):
            raise ValueError('Invalid gradient identifier.')
        paths = list(self.directory.glob(f'*--{identifier}.json'))
        if not paths:
            raise FileNotFoundError('Gradient not found.')
        if len(paths) != 1:
            raise Conflict('Multiple files have the same gradient identity.')
        document = json.loads(paths[0].read_text(encoding='utf-8'))
        validate(document)
        return document

    def list(self, query=''):
        documents = []
        for path in sorted(self.directory.glob('*.json')):
            doc = json.loads(path.read_text(encoding='utf-8'))
            validate(doc)
            words = list(doc['antonyms'].values()) + [i['concept'] for i in doc['gradient']]
            if query.casefold() in ' '.join(words).casefold():
                documents.append(doc)
        return documents

    def save(self, document):
        validate(document)
        doc = copy.deepcopy(document)
        with self.lock():
            try:
                old = self.load(doc['id'])
            except FileNotFoundError:
                old = None
            if old and (doc.get('modified_at') != old['modified_at'] or doc['endpoints'] != old['endpoints']):
                raise Conflict('This gradient already exists or changed elsewhere. Reload it from Saved Gradients before saving.')
            if not old and doc.get('modified_at') is not None:
                raise Conflict('The original saved gradient is missing.')
            now = datetime.now(timezone.utc).isoformat()
            doc['created_at'] = old['created_at'] if old else now
            doc['modified_at'] = now
            doc['gradient'].sort(key=lambda item: item['position'])
            path = self.path_for(doc)
            mirror = path.with_suffix('.md')
            previous = mirror.read_text(encoding='utf-8') if mirror.exists() else None
            try:
                atomic_write(mirror, markdown(doc))
                atomic_write(path, json.dumps(doc, indent=2, ensure_ascii=False) + '\n')
            except OSError:
                if previous is None:
                    mirror.unlink(missing_ok=True)
                else:
                    atomic_write(mirror, previous)
                raise
            return doc
