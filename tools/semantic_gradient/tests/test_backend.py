import copy
import json
import random
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.semantic_gradient.backend import (Conflict, GradientStore, ResourceUnavailable,
    WordNetService, atomic_write, endpoint, markdown, new_document, pair_id, validate)
from tools.semantic_gradient.server import make_server


class Lemma:
    def __init__(self, name, synset):
        self._name, self._synset, self.opposites = name, synset, []
    def name(self): return self._name
    def synset(self): return self._synset
    def key(self): return self._name + '%' + self._synset.name()
    def antonyms(self): return self.opposites
    def count(self): return 5


class Synset:
    def __init__(self, name, words):
        self._name = name
        self.words = [Lemma(word, self) for word in words]
        self.similar = []
    def name(self): return self._name
    def pos(self): return 'a'
    def definition(self): return 'Meaning of ' + self._name
    def lemmas(self): return self.words
    def similar_tos(self): return self.similar
    def also_sees(self): return []


class Corpus:
    def __init__(self):
        self.sets = []
        for i, (left, right) in enumerate([('cold', 'hot'), ('large', 'small'), ('dark', 'light'),
                                          ('fast', 'slow'), ('dry', 'wet'), ('bad', 'good'),
                                          ('long', 'short'), ('old', 'young'), ('high', 'low'), ('hard', 'soft')]):
            a, b = Synset(f'{left}.a.01', [left]), Synset(f'{right}.a.01', [right])
            a.words[0].opposites = [b.words[0]]
            b.words[0].opposites = [a.words[0]]
            self.sets.extend([a, b])
        cool = Synset('cool.a.01', ['cool', 'chilly'])
        self.sets[0].similar = [cool]
        self.sets.append(cool)
    def ensure_loaded(self): pass
    def all_synsets(self): return self.sets
    def synset(self, name): return next(s for s in self.sets if s.name() == name)


def fixture_document():
    corpus = Corpus()
    return new_document({'left': endpoint(corpus.sets[0].words[0]), 'right': endpoint(corpus.sets[1].words[0])})


def ambiguous_corpus():
    corpus = Corpus()
    cold = Synset('cold.a.02', ['cold'])
    hot = Synset('hot.a.02', ['hot'])
    warm = Synset('warm.a.01', ['warm'])
    cold.words[0].opposites = [hot.words[0], warm.words[0]]
    hot.words[0].opposites = [cold.words[0]]
    warm.words[0].opposites = [cold.words[0]]
    corpus.sets.extend([cold, hot, warm])
    return corpus


class ManualLookupTests(unittest.TestCase):
    def setUp(self): self.service = WordNetService(ambiguous_corpus())
    def test_case_insensitive_multiple_senses_and_reverse_deduplication(self):
        results = self.service.lookup('  CoLd  ')
        self.assertEqual(len(results), 3)
        self.assertEqual(len({r['document']['id'] for r in results}), 3)
        self.assertEqual({r['document']['endpoints']['left']['synset'] for r in results},
                         {'cold.a.01', 'cold.a.02'})
        hot = self.service.lookup('HOT')
        self.assertEqual(len(hot), 2)
        self.assertTrue({r['document']['id'] for r in hot}.issubset(r['document']['id'] for r in results))
        self.assertTrue(all('Meaning of' in r['senses']['left'] for r in results))
        results[0]['document']['gradient'].append({'concept': 'modified'})
        self.assertTrue(all(not r['document']['gradient'] for r in self.service.lookup('cold')))
    def test_single_missing_and_invalid_input(self):
        self.assertEqual(len(self.service.lookup('large')), 1)
        self.assertEqual(self.service.lookup('nonexistentword'), [])
        self.assertEqual(self.service.lookup('cool'), [])  # known word without direct antonyms
        for word in ('', '   ', None, 42, 'x' * 121):
            with self.subTest(word=word), self.assertRaises(ValueError): self.service.lookup(word)
    def test_phrase_normalization(self):
        left, right = Synset('all_right.a.01', ['all_right']), Synset('wrong.a.01', ['wrong'])
        left.words[0].opposites = [right.words[0]]
        self.service.corpus.sets.extend([left, right])
        self.assertEqual(self.service.lookup(' ALL   RIGHT '), self.service.lookup('all_right'))
        self.assertEqual(len(self.service.lookup('all right')), 1)
    def test_retained_pairs_never_return_in_fallback_sampling(self):
        retained = [r['document']['id'] for r in self.service.lookup('cold')]
        sampled = self.service.sample(50, retain=retained)
        self.assertTrue(sampled)
        self.assertTrue(set(retained).isdisjoint(d['id'] for d in sampled))
    def test_manual_lookup_persistence_and_provenance(self):
        doc = next(r['document'] for r in self.service.lookup('cold')
                   if r['document']['endpoints']['left']['synset'] == 'cold.a.01')
        doc['axis_origin'] = 'manual'
        candidate = self.service.suggestions(doc['endpoints'])[0]
        doc['gradient'] = [{**candidate, 'source': 'wordnet', 'position': .321987}]
        with tempfile.TemporaryDirectory() as directory:
            store = GradientStore(directory)
            saved = store.save(doc)
            loaded = store.load(saved['id'])
            self.assertEqual(loaded, saved)
            self.assertEqual(loaded['axis_origin'], 'manual')
            self.assertEqual(loaded['endpoints'], doc['endpoints'])
            self.assertEqual(loaded['gradient'], doc['gradient'])
            self.assertIn('similar_to', store.path_for(saved).with_suffix('.md').read_text())
            loaded['gradient'][0]['position'] = .7
            self.assertEqual(store.save(loaded)['gradient'][0]['position'], .7)


class WordNetTests(unittest.TestCase):
    def setUp(self): self.service = WordNetService(Corpus(), random.Random(42))
    def test_loading_deduplication_and_sampling(self):
        self.assertEqual(len(self.service.pairs()), 10)  # each relation occurs in both directions
        first = self.service.sample()
        second = self.service.sample(5, [d['id'] for d in first])
        self.assertEqual(len(first), 5)
        self.assertTrue({d['id'] for d in first}.isdisjoint(d['id'] for d in second))
        self.assertEqual(len(self.service.sample(50)), 10)
        with self.assertRaises(ValueError): self.service.sample(0)
        first[0]['gradient'].append({'concept': 'test'})
        self.assertTrue(all(not d['gradient'] for d in self.service.sample(10)))
    def test_suggestion_provenance(self):
        suggestions = self.service.suggestions(fixture_document()['endpoints'])
        self.assertEqual([s['concept'] for s in suggestions], ['chilly', 'cool'])
        p = suggestions[0]['provenance'][0]
        self.assertEqual(p['relation'], 'similar_to')
        self.assertEqual(p['from_synset'], 'cold.a.01')
        self.assertEqual(p['synset'], 'cool.a.01')
        self.assertNotIn('position', suggestions[0])
    def test_missing_wordnet(self):
        with patch.object(self.service.corpus, 'ensure_loaded', side_effect=LookupError):
            with self.assertRaisesRegex(ResourceUnavailable, 'nltk.downloader wordnet'):
                self.service.load()
    def test_reversed_identity(self):
        ends = fixture_document()['endpoints']
        self.assertEqual(pair_id(ends), pair_id({'left': ends['right'], 'right': ends['left']}))
    def test_duplicate_labels_distinct_senses(self):
        doc = fixture_document()
        other = copy.deepcopy(doc)
        other['endpoints']['left']['lemma_key'] += '2'
        other['id'] = pair_id(other['endpoints'])
        self.service._pairs = [(doc, 1), (other, 1)]
        self.assertEqual(len(self.service.sample(5)), 1)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = GradientStore(self.temp.name)
        self.doc = fixture_document()
        candidate = WordNetService(Corpus()).suggestions(self.doc['endpoints'])[0]
        self.doc['gradient'] = [{'concept': 'mild', 'position': 0.456789, 'source': 'manual'},
                                {**candidate, 'position': .2, 'source': 'wordnet'}]
    def test_roundtrip_markdown_search_update(self):
        saved = self.store.save(self.doc)
        self.assertEqual(saved, self.store.load(saved['id']))
        self.assertEqual(len(self.store.list('mild')), 1)
        self.assertEqual(len(self.store.list('COLD')), 1)
        self.assertEqual(self.store.list('absent'), [])
        md = self.store.path_for(saved).with_suffix('.md').read_text()
        self.assertIn('0.456789', md)
        self.assertIn('similar_to', md)
        self.assertIn('cold.a.01', md)
        saved['gradient'][0]['position'] = .3
        updated = self.store.save(saved)
        self.assertEqual(updated['created_at'], saved['created_at'])
        self.assertNotEqual(updated['modified_at'], saved['modified_at'])
        self.assertEqual(updated['gradient'][0]['position'], .3)
    def test_collision_and_stale_edit_protection(self):
        saved = self.store.save(self.doc)
        with self.assertRaises(Conflict): self.store.save(self.doc)
        self.store.save(saved)
        with self.assertRaises(Conflict): self.store.save(saved)
        other = copy.deepcopy(self.doc)
        other['endpoints']['left']['synset'] = 'cold.a.02'
        other['endpoints']['left']['lemma_key'] += '2'
        other['id'] = pair_id(other['endpoints'])
        self.store.save(other)
        self.assertEqual(len(list(Path(self.temp.name).glob('*.json'))), 2)
        self.assertNotEqual(self.store.path_for(other), self.store.path_for(saved))
    def test_failure_rolls_back_and_restart_repairs(self):
        saved = self.store.save(self.doc)
        path = self.store.path_for(saved)
        original = path.with_suffix('.md').read_text()
        saved['gradient'][0]['concept'] = 'changed'
        def fail_json(target, text):
            if target.suffix == '.json': raise OSError('disk full')
            atomic_write(target, text)
        with patch('tools.semantic_gradient.backend.atomic_write', side_effect=fail_json):
            with self.assertRaises(OSError): self.store.save(saved)
        self.assertEqual(path.with_suffix('.md').read_text(), original)
        self.assertNotEqual(self.store.load(saved['id'])['gradient'][0]['concept'], 'changed')
        path.with_suffix('.md').write_text('interrupted write')
        GradientStore(self.temp.name)
        self.assertEqual(path.with_suffix('.md').read_text(), original)
    def test_invalid_positions_and_provenance(self):
        for position in (0, 1, -1, float('nan'), float('inf'), True, '0.5'):
            self.doc['gradient'][0]['position'] = position
            with self.subTest(position=position), self.assertRaises(ValueError): self.store.save(self.doc)
        self.doc['gradient'][0]['position'] = .5
        self.doc['gradient'][1]['provenance'] = []
        with self.assertRaises(ValueError): validate(self.doc)
    def test_safe_paths_and_markdown(self):
        self.doc['gradient'][0]['concept'] = '<script>|\nhello'
        self.assertIn('&lt;script&gt;&#124; hello', markdown(self.doc))
        with self.assertRaises(ValueError): self.store.load('../../secret')


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = WordNetService(Corpus())
        self.server = make_server('127.0.0.1', 0, GradientStore(self.temp.name), self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()
    def request(self, path, data=None, headers=None):
        request = Request(self.url + path, data=None if data is None else json.dumps(data).encode(),
                          headers=headers or {'Content-Type': 'application/json'})
        with urlopen(request) as response: return json.load(response)
    def test_sample_save_reload_and_conflict(self):
        docs = self.request('/api/sample', {'count': 5})
        self.assertEqual(len(docs), 5)
        saved = self.request('/api/save', docs[0])
        self.assertEqual(self.request('/api/saved/' + saved['id']), saved)
        self.assertEqual(len(self.request('/api/saved')), 1)
        with self.assertRaises(HTTPError) as ctx: self.request('/api/save', docs[0])
        self.assertEqual(ctx.exception.code, 409)
    def test_manual_lookup_api(self):
        matches = self.request('/api/lookup', {'word': ' COLD '})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['document']['id'], fixture_document()['id'])
        self.assertEqual(self.request('/api/lookup', {'word': 'unknown'}), [])
        with self.assertRaises(HTTPError) as ctx: self.request('/api/lookup', {'word': ''})
        self.assertEqual(ctx.exception.code, 400)
        retained = [matches[0]['document']['id']]
        sampled = self.request('/api/sample', {'count': 50, 'retain': retained})
        self.assertTrue(set(retained).isdisjoint(d['id'] for d in sampled))

    def test_errors_and_cross_origin(self):
        with self.assertRaises(HTTPError) as ctx: self.request('/api/sample', {'count': -1})
        self.assertEqual(ctx.exception.code, 400)
        with self.assertRaises(HTTPError) as ctx:
            self.request('/api/save', fixture_document(), {'Content-Type': 'application/json', 'Origin': 'http://evil.example'})
        self.assertEqual(ctx.exception.code, 403)
        with patch.object(self.service, 'sample', side_effect=ResourceUnavailable('Install wordnet')):
            with self.assertRaises(HTTPError) as ctx: self.request('/api/sample', {})
            self.assertEqual(ctx.exception.code, 503)


if __name__ == '__main__': unittest.main()
