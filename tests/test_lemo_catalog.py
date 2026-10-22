import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import lemo_catalog as update
import lemo_reference as reference


class ReferenceUpdateTests(unittest.TestCase):
    def test_new_styles_are_discoverable_through_real_consumer(self):
        for query, slug in [('静音新闻', 'caption-news'), ('视觉调查', 'visual-investigation'),
                            ('实时倒计时', 'countdown'), ('战术讲解', 'telestrator'),
                            ('延时交响', 'city-symphony'), ('复古新闻', 'newsreel'),
                            ('构成主义蒙太奇', 'kino-montage'), ('电视新闻包装', 'news-package')]:
            with self.subTest(query=query):
                self.assertEqual(reference.search(query)['results'][0]['slug'], slug)

    def test_candidate_checks_actual_source_and_rejects_mutations_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, previous = root/'source', root/'previous'
            source.mkdir(); previous.mkdir()
            rows = [{'slug': 'test-style'}]
            content = {'styleboard/catalog.json': json.dumps(rows),
                       'styleboard/opuscar98_styles.json': '{"films": []}',
                       'styles/test-style/STYLE.md': 'A real mechanism\n',
                       'styles/test-style/DEMO.md': 'An example\n',
                       'LICENSE': 'MIT\n', 'README.md': 'Media: CC BY 4.0\n'}
            tree = {'tree': []}
            for path, text in content.items():
                p = source/path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
                tree['tree'].append({'path': path, 'type': 'blob', 'sha': update.blob(text.encode())})
            (previous/'catalog.json').write_text(json.dumps({'revision': 'a'*40, 'attribution': 'test', 'styles': []}))
            (previous/'LICENSE').write_text('MIT\n')
            card = dict(slug='test-style', aliases=['test'], refs=['styles/test-style/STYLE.md:1'])
            card.update({k: 'reviewed' for k in ['use_for', 'mechanism', 'visual', 'sound', 'needs', 'limits']})
            cards = root/'cards.json'
            good = {'styles': [card], 'basis': 'source review only'}
            cards.write_text(json.dumps(good))
            result = update.prepare(source, 'b'*40, cards, tree, root/'good', previous)
            self.assertEqual(result['style_count'], 1)
            self.assertEqual(result['added_styles'], ['test-style'])
            cases = []
            for mutation in ['empty', 'missing', 'line', 'path', 'template', 'duplicate']:
                data = copy.deepcopy(good)
                if mutation in ['empty', 'missing']: data['styles'] = []
                if mutation == 'line': data['styles'][0]['refs'] = ['styles/test-style/STYLE.md:2']
                if mutation == 'path': data['styles'][0]['refs'] = ['styles/test-style/../../LICENSE:1']
                if mutation == 'template': data['styles'][0]['slug'] = '_template'
                if mutation == 'duplicate': data['styles'].append(data['styles'][0])
                cases.append((mutation, data, tree, 'b'*40))
            cases += [('empty-tree', good, {'tree': []}, 'b'*40),
                      ('partial-tree', good, dict(tree, truncated=True), 'b'*40),
                      ('moving-version', good, tree, 'main')]
            for label, data, selected_tree, revision in cases:
                cards.write_text(json.dumps(data)); out = root/label
                with self.subTest(label=label), self.assertRaises(ValueError):
                    update.prepare(source, revision, cards, selected_tree, out, previous)
                self.assertFalse(out.exists())
            cards.write_text(json.dumps(good))
            (source/'styles/test-style/STYLE.md').write_text('Tampered\n')
            with self.assertRaisesRegex(ValueError, 'git blob'):
                update.prepare(source, 'b'*40, cards, tree, root/'tampered', previous)
            self.assertFalse((root/'tampered').exists())


if __name__ == '__main__':
    unittest.main()
