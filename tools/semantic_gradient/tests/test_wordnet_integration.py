"""Real corpus checks, deliberately fail with setup instructions if not installed."""
import unittest
from tools.semantic_gradient.backend import WordNetService, endpoint


class RealWordNetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = WordNetService()
        cls.corpus = cls.service.load()
    def test_real_sampling(self):
        pairs = self.service.sample(5)
        self.assertEqual(len(pairs), 5)
        for doc in pairs:
            left, right = doc['endpoints']['left'], doc['endpoints']['right']
            lemma = next(l for l in self.corpus.synset(left['synset']).lemmas() if l.key() == left['lemma_key'])
            reverse = next(l for l in self.corpus.synset(right['synset']).lemmas() if l.key() == right['lemma_key'])
            self.assertTrue(reverse in lemma.antonyms() or lemma in reverse.antonyms())
    def test_real_suggestions(self):
        cold = self.corpus.lemma('cold.a.01.cold')
        hot = cold.antonyms()[0]
        ends = {'left': endpoint(cold), 'right': endpoint(hot)}
        suggestions = self.service.suggestions(ends)
        self.assertTrue(suggestions)
        for candidate in suggestions:
            for p in candidate['provenance']:
                source = self.corpus.synset(p['from_synset'])
                target = self.corpus.synset(p['synset'])
                self.assertIn(p['lemma_key'], [l.key() for l in target.lemmas()])
                if p['relation'] == 'synonym': self.assertEqual(source, target)
                elif p['relation'] == 'similar_to': self.assertIn(target, source.similar_tos())
                elif p['relation'] == 'also_see': self.assertIn(target, source.also_sees())

    def test_real_manual_lookup(self):
        results = self.service.lookup(' COLD ')
        self.assertGreater(len(results), 1)
        for result in results:
            doc = result['document']
            self.assertIn('cold', doc['antonyms'].values())
            for side, ep in doc['endpoints'].items():
                self.assertEqual(result['senses'][side], self.corpus.synset(ep['synset']).definition())
                self.assertIn(ep['lemma_key'], [l.key() for l in self.corpus.synset(ep['synset']).lemmas()])
        self.assertEqual(self.service.lookup('zzzznotawordzzzz'), [])
