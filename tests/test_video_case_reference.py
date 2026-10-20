"""Exercise the public discovery/fetch/check path, including corrupt and empty inputs."""
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from email.message import Message
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import video_case_reference as cases


def stamp(payload, path):
    return {'path': path, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
            'git_blob': hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()}


class Response(BytesIO):
    def __init__(self, payload, url, mime='text/plain'):
        super().__init__(payload)
        self.url = url
        self.headers = Message()
        self.headers['Content-Type'] = mime

    def geturl(self):
        return self.url


class Discovery(unittest.TestCase):
    def test_real_catalog_chinese_retrieval_and_no_match(self):
        self.assertEqual(len(cases.catalog()['cases']), 8)
        result = cases.search('教学 空间关系 连续移动')
        self.assertEqual(result['results'][0]['id'], 'twoclipping-402193')
        self.assertLessEqual(len(result['results']), 3)
        self.assertEqual(cases.search('冰岛黑沙滩火山地质')['results'], [])
        self.assertTrue(all(r['code']['provided'] is False for r in result['results']))
        self.assertTrue(all(r['review']['audio']['status'] == 'not_reviewed' for r in result['results']))

    def test_limits_and_empty_queries(self):
        for query in ('', ' \n ', '??'):
            with self.subTest(query=query), self.assertRaises(ValueError): cases.search(query)
        for limit in (0, 6, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError): cases.search('教学', limit)

    def test_partial_and_post_description_are_opt_in(self):
        data = cases.catalog()
        for kind, partial in [('partial_prompt', True), ('post_description', False), ('unknown', False)]:
            fixture = copy.deepcopy(data)
            for row in fixture['cases']:
                row['content_kind'] = kind
                row['prompt_partial'] = partial
            with patch.object(cases, 'catalog', return_value=fixture):
                self.assertEqual(cases.search('教学')['results'], [])
                self.assertTrue(cases.search('教学', include_partial=True)['results'])

    def test_corrupt_catalog_rejected_by_real_loader(self):
        data = cases.catalog()
        changes = [None, {}, dict(data, cases=[]), dict(data, revision='main'),
                   dict(data, cases=[data['cases'][0], data['cases'][0]])]
        for field, value in [('id', '../../outside'), ('source', {'bytes': 0}), ('prompt_partial', 'false'),
                             ('review', {}), ('review', None), ('review', {'source': None}),
                             ('review', {'source': {'status': 'reviewed', 'evidence': ['fixture']},
                                         'visual': {'status': 'not_reviewed', 'evidence': []},
                                         'audio': {'status': 'not_reviewed', 'evidence': []},
                                         'local_reproduction': None}),
                             ('code', {'provided': True}), ('search', {})]:
            item = copy.deepcopy(data)
            item['cases'][0][field] = value
            changes.append(item)
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / 'catalog.json'
            for value in changes:
                catalog_path.write_text(json.dumps(value))
                with self.subTest(value=str(value)[:80]), patch.object(cases, 'CATALOG', catalog_path):
                    with self.assertRaises((ValueError, TypeError)): cases.search('教学')
            catalog_path.write_text('{broken')
            with patch.object(cases, 'CATALOG', catalog_path), self.assertRaises(ValueError): cases.info()

    def test_cli_failure_exit_code_and_success(self):
        script = str(Path(cases.__file__))
        result = subprocess.run([sys.executable, script, 'search', ''], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('nonempty', result.stderr)
        result = subprocess.run([sys.executable, script, 'search', '完全不相干火山地质'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['results'], [])


class Retrieval(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / 'cache'
        self.output = self.root / 'project/references/case'
        self.data = cases.catalog()
        self.row = self.data['cases'][0]
        self.prompt = b'# Reference\n\nA continuous object. Never executed.\n'
        self.license = b'MIT License\nFixture only.\n'
        self.row['source'].update(stamp(self.prompt, self.row['source']['path']))
        self.data['license'].update(stamp(self.license, 'LICENSE'))
        self.catalog_path = self.root / 'catalog.json'
        self.save_catalog()
        self.patcher = patch.object(cases, 'CATALOG', self.catalog_path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def save_catalog(self):
        self.catalog_path.write_text(json.dumps(self.data))

    def response(self, url, timeout):
        return Response(self.license if url.endswith('/LICENSE') else self.prompt, url)

    def fetch(self):
        with patch.object(cases.urllib.request, 'urlopen', side_effect=self.response) as network:
            result = cases.fetch(self.row['id'], self.output, self.cache)
        return result, network

    def test_valid_fetch_cached_offline_copy_and_check(self):
        result, network = self.fetch()
        self.assertEqual(network.call_count, 2)
        self.assertEqual(cases.check(result['receipt'])['status'], 'reference_bytes_verified')
        self.assertEqual((self.output / 'prompt.md').read_bytes(), self.prompt)
        with patch.object(cases.urllib.request, 'urlopen', side_effect=AssertionError('network forbidden')):
            offline = cases.fetch(self.row['id'], self.root / 'offline', self.cache, offline=True)
            self.assertEqual(cases.check(offline['receipt'])['origin_check'], 'current_pinned_catalog')

    def test_unknown_id_and_existing_output_are_never_overwritten(self):
        with patch.object(cases.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')):
            for case_id in ('../../outside', 'unknown-123456'):
                with self.assertRaisesRegex(ValueError, 'unknown'): cases.fetch(case_id, self.output, self.cache)
            self.output.mkdir(parents=True)
            (self.output / 'keep').write_text('preserve')
            with self.assertRaisesRegex(ValueError, 'already exists'): cases.fetch(self.row['id'], self.output, self.cache)
            self.assertEqual((self.output / 'keep').read_text(), 'preserve')

    def test_empty_offline_cache_fails_without_partial_package(self):
        with self.assertRaisesRegex(ValueError, 'not cached'):
            cases.fetch(self.row['id'], self.output, self.cache, offline=True)
        self.assertFalse(self.output.exists())

    def test_corrupt_cached_text_is_not_refetched_or_accepted(self):
        self.fetch()
        stored = self.cache / self.data['revision'] / self.row['source']['path']
        for mutation in (b'', b'changed'):
            stored.write_bytes(mutation)
            with patch.object(cases.urllib.request, 'urlopen', side_effect=AssertionError('refetch forbidden')):
                with self.assertRaisesRegex(ValueError, 'fingerprint'):
                    cases.fetch(self.row['id'], self.root / 'bad', self.cache)
            self.assertFalse((self.root / 'bad').exists())

    def test_mime_redirect_oversize_and_error_pages_fail_before_output(self):
        url = cases.RAW + self.data['revision'] + '/' + self.row['source']['path']
        for body, final_url, mime in [(self.prompt, url, 'text/html'),
                                      (self.prompt, 'https://unexpected.example/file', 'text/plain'),
                                      (self.prompt + b'x', url, 'text/plain'),
                                      (b'<html>Access denied</html>', url, 'text/plain'),
                                      (b'', url, 'text/plain')]:
            with self.subTest(mime=mime, url=final_url, body=body):
                with patch.object(cases.urllib.request, 'urlopen', return_value=Response(body, final_url, mime)):
                    with self.assertRaises(ValueError): cases.fetch(self.row['id'], self.output, self.cache)
                self.assertFalse(self.output.exists())

    def test_license_failure_cannot_leave_success_receipt(self):
        def denied_license(url, timeout):
            return Response(b'denied' if url.endswith('/LICENSE') else self.prompt, url)
        with patch.object(cases.urllib.request, 'urlopen', side_effect=denied_license):
            with self.assertRaises(ValueError): cases.fetch(self.row['id'], self.output, self.cache)
        self.assertFalse(self.output.exists())

    def test_write_failure_removes_only_new_output(self):
        original = Path.write_text
        def fail_receipt(path, *args, **kwargs):
            if path.name == 'SOURCE.json': raise OSError('simulated full disk')
            return original(path, *args, **kwargs)
        with patch.object(cases.urllib.request, 'urlopen', side_effect=self.response), patch.object(Path, 'write_text', fail_receipt):
            with self.assertRaisesRegex(OSError, 'full disk'): cases.fetch(self.row['id'], self.output, self.cache)
        self.assertFalse(self.output.exists())

    def test_project_mutations_fail_through_real_check_consumer(self):
        self.fetch()
        target = self.output / 'prompt.md'
        for mutation in (b'', b'new bytes'):
            target.write_bytes(mutation)
            with self.assertRaisesRegex(ValueError, 'fingerprint'): cases.check(self.output / 'SOURCE.json')
        target.unlink()
        with self.assertRaisesRegex(ValueError, 'missing'): cases.check(self.output / 'SOURCE.json')
        outside = self.root / 'outside'; outside.write_bytes(self.prompt); target.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'unsafe'): cases.check(self.output / 'SOURCE.json')

    def test_receipt_tampering_is_rejected(self):
        self.fetch()
        receipt_path = self.output / 'SOURCE.json'
        original = json.loads(receipt_path.read_text())
        changes = [dict(original, files=[]), dict(original, revision='0' * 40), dict(original, id='other-123456')]
        changed = copy.deepcopy(original); changed['files'][0]['project_path'] = '../../outside'; changes.append(changed)
        changed = copy.deepcopy(original); changed['files'][0]['sha256'] = '0' * 64; changes.append(changed)
        changed = copy.deepcopy(original); changed['files'][0]['git_blob'] = '0' * 40; changes.append(changed)
        for value in changes:
            receipt_path.write_text(json.dumps(value))
            with self.subTest(value=str(value)[:90]), self.assertRaises(ValueError): cases.check(receipt_path)

    def test_index_notes_change_does_not_invalidate_recorded_reference(self):
        self.fetch()
        self.row['title_zh'] = 'Updated editorial title'
        self.data['catalog_version'] = 'next-editorial-version'
        self.save_catalog()
        self.assertEqual(cases.check(self.output / 'SOURCE.json')['status'], 'reference_bytes_verified')


if __name__ == '__main__':
    unittest.main()
