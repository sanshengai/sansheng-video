import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from export_publish import export
from package_delivery import digest


class ExportTests(unittest.TestCase):
    def test_delivery_identity_and_refusals(self):
        # Contract fixture only; not evidence of actual video or platform verification.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('video.mp4','cover.png'): (root/name).write_bytes(b'fixture')
            report = dict(kind='video-delivery/1',review_status='user_accepted',review_source='fixture-feedback',
                          technical=dict(full_decode=True),video='video.mp4',poster='cover.png',
                          files={n:digest(root/n) for n in ('video.mp4','cover.png')},suggested_title='标题',summary='说明')
            delivery=root/'delivery.json'; delivery.write_text(json.dumps(report))
            targets=root/'targets.json'; targets.write_text(json.dumps(dict(targets=[dict(id='x',platform='x',account='test',endpoint='draft',content_type='video')])))
            path=export(delivery,targets,root/'publish.json')
            self.assertEqual(export(delivery,targets,path),path)
            value=json.loads(path.read_text()); self.assertEqual(value['targets'][0]['asset_ids'],['video','cover'])
            (root/'video.mp4').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'已改变'): export(delivery,targets,path)
            report['review_status']='candidate'; delivery.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'已接受'): export(delivery,targets,path)


if __name__ == '__main__': unittest.main()
