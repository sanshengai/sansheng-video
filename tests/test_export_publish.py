import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from export_publish import export
from package_delivery import digest, copy_subtitles


class ExportTests(unittest.TestCase):
    def test_subtitles_copy_export_and_changed_file_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'source'; source.mkdir(); delivery_root=root/'delivery'; delivery_root.mkdir()
            (source/'captions.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\n字幕\n')
            rows,hashes=copy_subtitles({'subtitles':[{'path':'captions.srt','language':'zh-CN'}]},source,delivery_root)
            for name in ('video.mp4','cover.png'): (delivery_root/name).write_bytes(b'fixture')
            report=dict(kind='video-delivery/1',review_status='user_accepted',review_source='fixture-feedback',
                        technical={'full_decode':True},video='video.mp4',poster='cover.png',subtitles=rows,
                        files={**hashes,**{n:digest(delivery_root/n) for n in ('video.mp4','cover.png')}},suggested_title='标题',summary='说明')
            delivery=delivery_root/'delivery.json'; delivery.write_text(json.dumps(report))
            targets=root/'targets.json'; targets.write_text(json.dumps({'targets':[dict(id='b',platform='bilibili',account='test',endpoint='draft',content_type='video')]}))
            result=export(delivery,targets,root/'manifest.json')
            manifest=json.loads(result.read_text()); self.assertEqual(manifest['assets'][-1]['language'],'zh-CN')
            self.assertIn('subtitle-1',manifest['targets'][0]['asset_ids'])
            (delivery_root/rows[0]['path']).write_text('changed')
            with self.assertRaisesRegex(ValueError,'已改变'): export(delivery,targets,result)

    def test_subtitle_selection_is_explicit_and_unambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'one.srt').write_text('subtitle')
            self.assertEqual(copy_subtitles({},root,root),([],{}))
            for rows in ([{'path':'one.srt','language':'../escape'}],
                         [{'path':'one.srt','language':'zh'},{'path':'one.srt','language':'ZH'}],
                         [{'path':'missing.srt','language':'zh'}]):
                with self.assertRaises(ValueError): copy_subtitles({'subtitles':rows},root,root)

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
