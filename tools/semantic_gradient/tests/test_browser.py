"""Chromium interaction tests against the real HTTP server and isolated persistence."""
import json
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright, expect
from tools.semantic_gradient.backend import GradientStore, WordNetService
from tools.semantic_gradient.server import make_server
from test_backend import Corpus, fixture_document, ambiguous_corpus


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()
    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.playwright.stop()
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = GradientStore(self.temp.name)
        service = self.service = WordNetService(Corpus())
        # Deterministic corpus includes an axis with known candidate provenance.
        service._pairs = [(fixture_document(), 100000)] + service.pairs()[1:]
        self.server = make_server('127.0.0.1', 0, self.store, service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.context = self.browser.new_context(viewport={'width': 1100, 'height': 900})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.goto(f'http://127.0.0.1:{self.server.server_port}')
        expect(self.page.locator('.card')).to_have_count(5)
        self.card = self.page.locator(f'.card[data-id="{fixture_document()["id"]}"]')
        expect(self.card).to_be_visible()
    def tearDown(self):
        self.context.close()
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])
    def add(self, name, position=.5, card=None):
        card = card if card is not None else self.card
        axis = card.locator('.axis')
        axis.click(position={'x': axis.bounding_box()['width'] * position, 'y': 8})
        self.page.locator('#concept-word').fill(name)
        self.page.locator('#concept-position').fill(str(position))
        self.page.get_by_role('button', name='Apply', exact=True).click()
    def test_edit_move_delete_and_independent_axes(self):
        self.add('mild', .456789)
        second = self.page.locator('.card').nth(1)
        self.add('other axis', .3, second)
        node = self.card.locator('.concept')
        node.click()
        self.page.locator('#concept-word').fill('temperate')
        self.page.locator('#concept-position').fill('.65')
        self.page.get_by_role('button', name='Apply', exact=True).click()
        expect(node).to_have_text('temperate')
        self.assertAlmostEqual(float(node.get_attribute('data-position')), .65)
        rect, axis = node.bounding_box(), self.card.locator('.axis').bounding_box()
        self.page.mouse.move(rect['x'] + rect['width']/2, rect['y'] + rect['height']/2)
        self.page.mouse.down()
        self.page.mouse.move(axis['x'] + axis['width']*.25, rect['y'] + rect['height']/2, steps=10)
        self.page.mouse.up()
        expect(node).to_have_attribute('data-position', '0.25')
        expect(self.page.locator('#concept-dialog')).not_to_be_visible()
        node.click(); self.page.get_by_role('button', name='Delete', exact=True).click()
        expect(self.card.locator('.concept')).to_have_count(0)
        expect(second.locator('.concept')).to_have_text('other axis')
    def test_suggestions_save_search_reload_and_provenance(self):
        self.add('mild', .456789)
        self.card.get_by_role('button', name='Suggest Concepts').click()
        candidates = self.card.locator('.candidate')
        expect(candidates).to_have_count(2)
        expect(self.card.locator('.concept')).to_have_count(1)
        candidates.filter(has_text='cool').click()
        axis = self.card.locator('.axis')
        axis.click(position={'x': axis.bounding_box()['width']*.25, 'y': 8})
        expect(self.card.locator('.concept.wordnet')).to_have_text('cool')
        # Exercise native HTML drag/drop for the other candidate.
        candidates.filter(has_text='chilly').drag_to(axis, target_position={'x': axis.bounding_box()['width']*.75, 'y': 8})
        expect(self.card.locator('.concept')).to_have_count(3)
        self.page.get_by_role('button', name='Save All', exact=True).click()
        expect(self.page.locator('#message')).to_have_text('Saved 5 gradients.')
        saved = self.store.load(fixture_document()['id'])
        manual = next(i for i in saved['gradient'] if i['concept'] == 'mild')
        self.assertEqual(manual['position'], .456789)
        accepted = next(i for i in saved['gradient'] if i['concept'] == 'cool')
        self.assertEqual(accepted['provenance'][0]['relation'], 'similar_to')
        self.page.get_by_role('button', name='Resample', exact=True).click()
        expect(self.page.locator('#message')).to_contain_text('Sampled 5 pairs.')
        self.page.get_by_role('button', name='Saved Gradients', exact=True).click()
        self.page.locator('#search').fill('mild')
        self.page.get_by_role('button', name='Search', exact=True).click()
        expect(self.page.locator('.saved-row')).to_have_count(1)
        self.page.get_by_role('button', name='Load', exact=True).click()
        expect(self.card.locator('.concept')).to_have_count(3)
        self.card.locator('.concept').filter(has_text='mild').click()
        expect(self.page.locator('#concept-position')).to_have_value('0.456789')
        self.page.locator('#concept-position').fill('.6')
        self.page.get_by_role('button', name='Apply', exact=True).click()
        self.card.get_by_role('button', name='Save', exact=True).click()
        expect(self.card.locator('.state')).to_have_text('Saved')
        reloaded = self.store.load(saved['id'])
        self.assertEqual(next(i for i in reloaded['gradient'] if i['concept'] == 'cool'), accepted)
        self.assertEqual(reloaded['created_at'], saved['created_at'])
    def test_unsaved_protection_and_count(self):
        self.add('keep me')
        identifiers = self.page.locator('.card').evaluate_all('(nodes) => nodes.map(n => n.dataset.id)')
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        self.page.get_by_role('button', name='Resample', exact=True).click()
        expect(self.card.locator('.concept')).to_have_text('keep me')
        self.assertEqual(identifiers, self.page.locator('.card').evaluate_all('(nodes) => nodes.map(n => n.dataset.id)'))
        self.page.locator('#count').fill('3')
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.page.get_by_role('button', name='Resample', exact=True).click()
        expect(self.page.locator('.card')).to_have_count(3)
        # A reload fires the beforeunload guard; cancellation retains edits.
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        self.page.evaluate('window.location.reload()')
        expect(self.page.locator('.card')).to_have_count(3)
    def test_dense_labels_mobile_and_rename_origin(self):
        self.page.set_viewport_size({'width': 390, 'height': 850})
        for i in range(7): self.add(f'Long concept phrase {i}', .5)
        boxes = self.card.locator('.concept').evaluate_all('(nodes) => nodes.map(n => { const r=n.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}; })')
        for i, a in enumerate(boxes):
            for b in boxes[i+1:]:
                self.assertTrue(a['right'] <= b['left'] or b['right'] <= a['left'] or a['bottom'] <= b['top'] or b['bottom'] <= a['top'])
        self.assertTrue(all(b['left'] >= 0 and b['right'] <= 390 for b in boxes))
        self.card.get_by_role('button', name='Suggest Concepts').click()
        self.card.locator('.candidate').filter(has_text='cool').click()
        self.card.locator('.axis').focus(); self.page.keyboard.press('Enter')
        self.card.locator('.concept.wordnet').click()
        self.page.locator('#concept-word').fill('my interpretation')
        self.page.get_by_role('button', name='Apply', exact=True).click()
        self.card.get_by_role('button', name='Save', exact=True).click()
        expect(self.card.locator('.state')).to_have_text('Saved')
        item = next(i for i in self.store.load(fixture_document()['id'])['gradient'] if i['concept'] == 'my interpretation')
        self.assertEqual(item['source'], 'manual')
        self.assertEqual(item['origin']['concept'], 'cool')
        self.assertTrue(item['origin']['provenance'])
    def test_failed_resample_preserves_edits(self):
        self.add('preserved')
        self.page.route('**/api/sample', lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'error': 'WordNet unavailable'})))
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.page.get_by_role('button', name='Resample', exact=True).click()
        expect(self.page.locator('#message')).to_have_text('WordNet unavailable')
        expect(self.card.locator('.concept')).to_have_text('preserved')

    def test_reload_confirmation_and_failed_save_keep_edits(self):
        self.add('original')
        self.card.get_by_role('button', name='Save', exact=True).click()
        expect(self.card.locator('.state')).to_have_text('Saved')
        self.add('unsaved')
        self.page.get_by_role('button', name='Saved Gradients', exact=True).click()
        expect(self.page.locator('.saved-row')).to_have_count(1)
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        self.page.get_by_role('button', name='Load', exact=True).click()
        self.page.get_by_role('button', name='Editor', exact=True).click()
        expect(self.card.locator('.concept')).to_have_count(2)
        self.page.route('**/api/save', lambda route: route.fulfill(status=500, content_type='application/json', body=json.dumps({'error': 'Disk full'})))
        self.card.get_by_role('button', name='Save', exact=True).click()
        expect(self.page.locator('#message')).to_have_text('Disk full')
        expect(self.card.locator('.state')).to_have_text('Unsaved changes')
        expect(self.card.locator('.concept')).to_have_count(2)
        self.assertEqual(len(self.store.load(fixture_document()['id'])['gradient']), 1)
        self.page.get_by_role('button', name='Saved Gradients', exact=True).click()
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.page.get_by_role('button', name='Load', exact=True).click()
        expect(self.card.locator('.concept')).to_have_count(1)
        expect(self.card.locator('.state')).to_have_text('Saved')

    def test_endpoint_labels_have_readable_width(self):
        for width in (1100, 390):
            self.page.set_viewport_size({'width': width, 'height': 900})
            labels = self.page.locator('.endpoint').evaluate_all("""nodes => nodes.map(n => {
                const r = n.getBoundingClientRect();
                const axis = n.closest('.axis').getBoundingClientRect();
                return {width: r.width, height: r.height, bottom: r.bottom, axisTop: axis.top};
            })""")
            for label in labels:
                self.assertGreater(label['width'], 20)
                self.assertLess(label['height'], 60)
                self.assertLess(label['bottom'], label['axisTop'])

    def lookup(self, word):
        self.page.locator('#lookup-word').fill(word)
        self.page.get_by_role('button', name='Find Antonyms', exact=True).click()

    def test_manual_duplicate_resample_save_reload(self):
        self.add('keep this position', .321987)
        self.lookup(' COLD ')
        expect(self.card.locator('.manual-state')).to_be_visible()
        expect(self.page.locator('.card')).to_have_count(5)
        self.lookup('hot')
        expect(self.page.locator('#lookup-status')).to_contain_text('already open')
        expect(self.page.locator('.card')).to_have_count(5)
        self.card.get_by_role('button', name='Suggest Concepts').click()
        self.card.locator('.candidate').filter(has_text='cool').click()
        self.card.locator('.axis').focus(); self.page.keyboard.press('Enter')
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.page.get_by_role('button', name='Resample', exact=True).click()
        expect(self.page.locator('.card')).to_have_count(6)
        expect(self.card.locator('.concept')).to_have_count(2)
        expect(self.card.locator('.concept').filter(has_text='keep this position')).to_have_attribute('data-position', '0.321987')
        self.card.get_by_role('button', name='Save', exact=True).click()
        expect(self.card.locator('.state').first).to_contain_text('Manual')
        expect(self.card.locator('.state').last).to_have_text('Saved')
        saved = self.store.load(fixture_document()['id'])
        self.assertEqual(saved['axis_origin'], 'manual')
        # Start a fresh editor to ensure retention metadata survives persistence.
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.page.reload()
        expect(self.page.locator('.card')).to_have_count(5)
        self.page.get_by_role('button', name='Saved Gradients', exact=True).click()
        expect(self.page.locator('.saved-row')).to_have_count(1)
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.page.get_by_role('button', name='Load', exact=True).click()
        expect(self.card.locator('.manual-state')).to_be_visible()
        expect(self.card.locator('.concept')).to_have_count(2)
        self.card.locator('.concept.wordnet').click()
        self.page.locator('#concept-position').fill('.8')
        self.page.get_by_role('button', name='Apply', exact=True).click()
        self.card.get_by_role('button', name='Save', exact=True).click()
        expect(self.card.locator('.state').last).to_have_text('Saved')
        updated = self.store.load(saved['id'])
        self.assertEqual(updated['gradient'][-1]['position'], .8)
        self.assertEqual(updated['gradient'][-1]['provenance'], saved['gradient'][-1]['provenance'])

    def test_manual_multiple_senses_and_missing_result(self):
        self.service.corpus = ambiguous_corpus(); self.service._pairs = None
        self.lookup('notaword')
        expect(self.page.locator('#lookup-status')).to_contain_text('No WordNet antonyms found')
        expect(self.page.locator('.card')).to_have_count(5)
        self.lookup('cold')
        expect(self.page.locator('.lookup-result')).to_have_count(3)
        expect(self.page.locator('.card')).to_have_count(5)
        choice = self.page.locator('.lookup-result').filter(has_text='warm.a.01')
        expect(choice).to_contain_text('cold.a.02: Meaning of cold.a.02')
        choice.get_by_role('button', name='Add Pair', exact=True).click()
        expect(self.page.locator('.card')).to_have_count(6)
        expect(self.page.locator('.manual-state')).to_have_count(1)
        choice.get_by_role('button', name='Add Pair', exact=True).click()
        expect(self.page.locator('.card')).to_have_count(6)
        self.lookup('cool')
        expect(self.page.locator('#lookup-status')).to_contain_text('No WordNet antonyms found')
        expect(self.page.locator('.lookup-result')).to_have_count(0)
        expect(self.page.locator('.card')).to_have_count(6)

    def test_manual_unsaved_axis_needs_no_discard_on_resample(self):
        self.page.get_by_role('button', name='Save All', exact=True).click()
        expect(self.page.locator('#message')).to_have_text('Saved 5 gradients.')
        self.lookup('cold')
        expect(self.card.locator('.manual-state')).to_be_visible()
        self.add('unsaved manual')
        dialogs = []
        self.page.on('dialog', lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
        self.page.get_by_role('button', name='Resample', exact=True).click()
        expect(self.page.locator('.card')).to_have_count(6)
        expect(self.card.locator('.concept')).to_have_text('unsaved manual')
        self.assertEqual(dialogs, [])
