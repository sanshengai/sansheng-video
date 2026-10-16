import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

MODULE = Path(__file__).resolve().parents[1]/'scripts/openverse_audio.py'
spec = importlib.util.spec_from_file_location('openverse_audio', MODULE)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class AudioWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.record = {'id':'test', 'title':'click', 'creator':'Example', 'license':'cc0', 'url':'https://example.com/click.wav', 'foreign_landing_url':'https://example.com/click', 'license_url':'https://creativecommons.org/publicdomain/zero/1.0/'}
        source = self.root/'source.wav'
        with wave.open(str(source), 'wb') as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000); stream.writeframes(b'\0\0'*800)
        self.wav = source.read_bytes()

    def test_browser_results_require_explicit_selection(self):
        with self.assertRaises(ValueError):
            mod.select({'results':[self.record, dict(self.record,id='other')]},None)
        self.assertEqual(mod.select({'results':[self.record]},'test')['id'],'test')

    def test_empty_record_and_unknown_id(self):
        for data, ident in [([],None), ({'results':[]},None), ([self.record],'unknown')]:
            with self.assertRaises(ValueError):
                mod.select(data, ident)

    def test_restricted_license_and_missing_provenance(self):
        for record in [dict(self.record,license='by-nc'),dict(self.record,foreign_landing_url='')]:
            with self.assertRaises(ValueError):
                mod.select(record,None)

    def test_download_cache_and_receipt_do_not_claim_review(self):
        with patch.object(mod,'read_url',return_value=self.wav) as request:
            first = mod.fetch(self.record,self.root/'a.wav',self.root/'cache')
            second = mod.fetch(self.record,self.root/'b.wav',self.root/'cache')
            self.assertEqual(request.call_count,1)
        self.assertEqual(first['sha256'],second['sha256'])
        receipt = json.loads((self.root/'a.wav.source.json').read_text())
        self.assertIn('pending',receipt['source_review'])
        self.assertEqual(receipt['listening_status'],'pending')
        self.assertAlmostEqual(first['duration'],.1)

    def test_html_error_is_not_saved_as_audio(self):
        with patch.object(mod,'read_url',return_value=b'<html>Access denied</html>'):
            with self.assertRaises(ValueError):
                mod.fetch(self.record,self.root/'bad.mp3',self.root/'cache')
        self.assertFalse((self.root/'bad.mp3').exists())
        self.assertFalse((self.root/'bad.mp3.source.json').exists())

    def test_empty_download_rejected(self):
        with patch.object(mod,'read_url',return_value=b''):
            with self.assertRaises(ValueError):
                mod.fetch(self.record,self.root/'empty.mp3',self.root/'cache')

    def test_existing_output_untouched(self):
        output = self.root/'keep.wav'; output.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            mod.fetch(self.record,output,self.root/'cache')
        self.assertEqual(output.read_bytes(),b'keep')

    def test_search_cache_and_bounded_results(self):
        with patch.object(mod,'read_url',return_value=json.dumps({'results':[self.record]}).encode()) as request:
            mod.search('click',3,self.root/'cache'); mod.search('click',3,self.root/'cache')
            self.assertEqual(request.call_count,1)
            self.assertIn('page_size=3',request.call_args.args[0])

    def test_network_failure_points_to_browser(self):
        with patch.object(mod,'read_url',side_effect=OSError('HTTP 403')):
            with self.assertRaisesRegex(ValueError,'browser.*fetch --record'):
                mod.search('click',3,self.root/'cache')

    def test_insecure_url_rejected_before_request(self):
        with self.assertRaises(ValueError):
            mod.read_url('http://example.com/click.wav')
