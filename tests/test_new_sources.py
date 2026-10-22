import sys
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import synthesize_narration as tts
import stock_media as stock
import lemo_reference as lemo

class NarrationInput(unittest.TestCase):
    def test_empty_and_malformed_inputs_are_refused(self):
        for blocks in ([], [''], ['  '], [None], ['x'*401]):
            with self.subTest(blocks=blocks), self.assertRaises(ValueError):
                tts.validate({'engine':'voxcpm2','blocks':blocks})
        for change in ({'seed':True},{'engine':'other'},{'reference':'voice.wav'},
                       {'engine':'kokoro','voice':'../../bad'}, {'engine':'kokoro','language':'z','voice':'af_heart'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                tts.validate(dict({'engine':'voxcpm2','blocks':['hello']},**change))
    def test_authorized_reference_and_explicit_blocks(self):
        self.assertEqual(tts.validate({'engine':'voxcpm2','blocks':['你好','Hello'],'reference':'own.wav','reference_rights':'Own recording'}),['你好','Hello'])

class StockInput(unittest.TestCase):
    def test_missing_key_is_same_source_browser_route(self):
        with patch.dict('os.environ',{},clear=True), tempfile.TemporaryDirectory() as d:
            r=stock.search('quiet city','landscape',d)
        self.assertEqual(r['status'],'browser_required')
        self.assertTrue(r['url'].startswith('https://www.pexels.com/'))
    def test_empty_query_refused(self):
        with self.assertRaises(ValueError):stock.search('  ','portrait','unused')
    def test_provider_receipt_and_media_required(self):
        rec={'provider':'pexels','id':'1','creator':'Creator','page_url':'https://www.pexels.com/video/1/','license_url':stock.LICENSES['pexels'],'url':'https://example.com/a.mp4'}
        with tempfile.TemporaryDirectory() as d:
            for change in ({'provider':'unknown'},{'license_url':''},{'page_url':'https://evil.example/'}):
                with self.assertRaises(ValueError):stock.fetch(dict(rec,**change),Path(d)/'bad.mp4')
            with patch.object(stock,'read',return_value=b'<html>Denied</html>'),self.assertRaises(ValueError):
                stock.fetch(rec,Path(d)/'bad.mp4')
            self.assertFalse((Path(d)/'bad.mp4').exists())
            keep=Path(d)/'keep.mp4';keep.write_bytes(b'keep')
            with self.assertRaises(ValueError):stock.fetch(rec,keep)
            self.assertEqual(keep.read_bytes(),b'keep')

class LemoReference(unittest.TestCase):
    def test_catalog_counts_and_bounded_search(self):
        data=lemo.catalog();self.assertEqual(len(data['styles']),59);self.assertEqual(len(data['cinema']['films']),98)
        self.assertEqual(lemo.search('白板')['results'][0]['slug'],'whiteboard')
        self.assertLessEqual(len(lemo.search('film')['results']),3)
        self.assertEqual(lemo.search('no-such-reference-xyz')['results'],[])
        for value in ('','  '):
            with self.assertRaises(ValueError):lemo.search(value)
    def test_unknown_style_and_corrupt_cached_source_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):lemo.fetch('../../x',root/'bad')
            row=next(r for r in lemo.catalog()['styles'] if r['slug']=='whiteboard')
            file=next(f for f in row['files'] if f['path'].endswith('/STYLE.md'))
            cache=root/'cache'/lemo.catalog()['revision']/file['path'];cache.parent.mkdir(parents=True);cache.write_bytes(b'corrupted')
            with self.assertRaisesRegex(ValueError,'fingerprint'):lemo.fetch('whiteboard',root/'ref',cache=root/'cache')
            self.assertFalse((root/'ref'/'SOURCE.json').exists())
