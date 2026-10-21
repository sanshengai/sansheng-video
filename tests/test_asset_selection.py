import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import select_assets as assets
import selection_preview
import production_timeline as production


class SelectionTests(unittest.TestCase):
    def fixture(self, root):
        records = []
        for ident, color, size in [('red', '#ff0000', (160, 90)), ('blue', '#0000ff', (90, 160))]:
            file = root/(ident+'.png'); Image.new('RGB', size, color).save(file)
            records.append({'id': ident, 'root': 'samples', 'path': file.name, 'kind': 'image',
                            'availability': 'available', 'sha256': assets.digest(file),
                            'width': size[0], 'height': size[1], 'aspect': size[0]/size[1],
                            'purpose': 'cover', 'topic': 'Example', 'rights': {'sample_use': 'unknown'}})
        catalog = root/'catalog.json'
        catalog.write_text(json.dumps({'kind': 'sample-catalog/1', 'roots': {'samples': str(root)},
                                      'assets': records, 'groups': []}))
        return catalog

    def make_lock(self, root, catalog, ident='red', name='selection'):
        selection = root/(name+'.json')
        selection.write_text(json.dumps({'kind': 'asset-selection/1', 'canvas': [160, 90],
                                         'items': [{'asset_id': ident}]}))
        lock = root/(name+'.lock.json'); assets.lock(catalog, selection, lock)
        return lock

    def test_sheet_and_selection_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); catalog = self.fixture(root)
            out = assets.sheet(catalog, root/'sheet.png', aspect='9:16', limit=1)
            self.assertEqual(1, out['shown'])
            self.assertEqual('blue', json.loads(Path(out['index']).read_text())['shown'][0]['id'])
            with self.assertRaisesRegex(ValueError, 'no matching'):
                assets.sheet(catalog, root/'empty.png', purpose='ppt')
            lock = self.make_lock(root, catalog)
            self.assertEqual('red', assets.verified(lock)[0]['items'][0]['asset_id'])
            original = (root/'red.png').read_bytes(); (root/'red.png').unlink()
            with self.assertRaisesRegex(ValueError, 'missing or changed'):
                assets.verified(lock)
            (root/'red.png').write_bytes(original)
            empty = root/'empty.json'; empty.write_text('{"kind":"asset-selection/1","canvas":[160,90],"items":[]}')
            with self.assertRaisesRegex(ValueError, 'nonempty'):
                assets.lock(catalog, empty, root/'empty.lock.json')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for real consumer mutation test')
    def test_actual_preview_changes_and_deleted_input_blocks_real_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); catalog = self.fixture(root)
            outputs = []
            for name in ('red', 'blue'):
                lock = self.make_lock(root, catalog, name, name)
                output = root/(name+'.mp4')
                selection_preview.render(lock, output, .5, 10)
                raw = subprocess.run(['ffmpeg','-v','error','-i',str(output),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],
                                     check=True, capture_output=True).stdout
                center = (45*160+80)*3; outputs.append(tuple(raw[center:center+3]))
            self.assertGreater(outputs[0][0], 200); self.assertLess(outputs[0][2], 30)
            self.assertGreater(outputs[1][2], 200); self.assertLess(outputs[1][0], 30)
            (root/'red.png').unlink()
            with self.assertRaisesRegex(ValueError, 'missing or changed'):
                selection_preview.render(root/'red.lock.json', root/'deleted.mp4', .5, 10)
            self.assertFalse((root/'deleted.mp4').exists())

    def test_actual_timeline_reads_selection_and_invalidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); catalog = self.fixture(root)
            lock = self.make_lock(root, catalog)
            source = root/'timeline.json'
            data = {'fps': 24, 'duration': 1, 'canvas': [160,90], 'requires_audio': False,
                    'asset_selection': lock.name, 'shots': [{'id':'one','start':0,'end':1}],
                    'events':[{'id':'one','scene_id':'one','start':0,'end':1,
                               'visual':{'type':'artwork','asset_ids':['red']},'timing_basis':'authored'}]}
            source.write_text(json.dumps(data)); dest = root/'derived'
            production.export(source, dest)
            self.assertIn('red.png', (dest/'events.js').read_text())
            data['events'][0]['visual']['asset_ids'] = ['unknown']; source.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'reference selected'):
                production.export(source, dest, refresh=True)
            data['events'][0]['visual']['asset_ids'] = ['red']; source.write_text(json.dumps(data))
            (root/'red.png').unlink()
            with self.assertRaisesRegex(ValueError, 'missing or changed'):
                production.export(source, dest, refresh=True)


if __name__ == '__main__':
    unittest.main()
