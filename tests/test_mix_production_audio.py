import array
import json
import math
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mix_production_audio as mixer


def samples(path):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0',
                             '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'], capture_output=True, check=True)
    values = array.array('f'); values.frombytes(result.stdout)
    return values


def amplitude(values, frequency, start, end):
    section = values[round(start*48000):round(end*48000)]
    angle = 2*math.pi*frequency/48000
    real = sum(value*math.cos(angle*i) for i, value in enumerate(section))
    imag = sum(value*math.sin(angle*i) for i, value in enumerate(section))
    return 2*math.hypot(real, imag)/len(section)


class MixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.video, cls.source, cls.voice, cls.music = [cls.root/name for name in ('video.mp4','source.mp4','voice.wav','music.wav')]
        mixer.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=30:d=6',
                   '-c:v','libx264','-pix_fmt','yuv420p',str(cls.video)])
        mixer.run(['ffmpeg','-v','error','-i',str(cls.video),'-f','lavfi','-i','sine=frequency=300:sample_rate=48000:duration=6',
                   '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac',str(cls.source)])
        mixer.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=700:sample_rate=48000:duration=6',
                   '-af',"volume='if(between(t,1,2)+between(t,4,5),1,0)':eval=frame",str(cls.voice)])
        mixer.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=1000:sample_rate=48000:duration=6',str(cls.music)])
        cls.result = cls.root/'mixed.mp4'
        cls.receipt = mixer.mix(cls.video, cls.voice, cls.music, cls.result, [[1,2],[4,5]], music_gain=.6, duck_gain=.12)
        cls.values = samples(cls.result)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_music_drops_during_both_voice_blocks_and_recovers_in_gap(self):
        levels = [amplitude(self.values,1000,a,b) for a,b in ((.3,.7),(1.3,1.7),(2.6,3.0),(4.3,4.7),(5.3,5.7))]
        self.assertLess(levels[1]/levels[0], .3)
        self.assertLess(levels[3]/levels[2], .3)
        self.assertGreater(levels[2]/levels[0], .9)
        self.assertGreater(levels[4]/levels[0], .9)
        self.assertGreater(amplitude(self.values,700,1.3,1.7), .1)

    def test_video_packets_and_duration_preserved_not_shortest(self):
        self.assertEqual(mixer.video_hash(self.video), mixer.video_hash(self.result))
        self.assertAlmostEqual(6,float(mixer.probe(self.result)['format']['duration']),places=2)
        self.assertGreater(amplitude(self.values,1000,5.5,5.8), .05)
        self.assertEqual('mixed_not_reviewed',self.receipt['status'])
        self.assertEqual(mixer.digest(self.result),self.receipt['output_sha256'])

    def test_sample_ramps_predduck_release_and_close_intervals_take_minimum(self):
        baseline=amplitude(self.values,1000,.3,.7)
        pre=[amplitude(self.values,1000,a,b)/baseline
             for a,b in ((.905,.925),(.945,.965),(.985,1.005))]
        self.assertGreater(pre[0],pre[1]+.15)
        self.assertGreater(pre[1],pre[2]+.15)
        self.assertLess(pre[2],.3)  # At speech start ducking is already complete.
        post=[amplitude(self.values,1000,a,b)/baseline
              for a,b in ((2.01,2.03),(2.11,2.13),(2.23,2.25))]
        self.assertLess(post[0],post[1]-.15)
        self.assertLess(post[1],post[2]-.15)
        close=self.root/'close-intervals.mp4'
        receipt=mixer.mix(self.video,self.voice,self.music,close,[[1,2],[2.08,3]],
                          music_gain=.6,duck_gain=.12)
        values=samples(close)
        for start in (2.0,2.02,2.04,2.06):
            self.assertLess(amplitude(values,1000,start,start+.02)/baseline,.5)
        self.assertGreater(amplitude(values,1000,3.4,3.6)/baseline,.9)
        self.assertAlmostEqual(6,float(mixer.probe(close)['format']['duration']),places=2)
        self.assertEqual(.1,receipt['attack'])
        self.assertEqual(.25,receipt['release'])
        self.assertEqual('sample_linear_minimum',receipt['duck_envelope'])

    def test_cli_passes_narration_gain_and_envelope_parameters(self):
        intervals=self.root/'cli-intervals.json'
        intervals.write_text('[[1,2]]')
        argv=['mix','--video',str(self.video),'--narration',str(self.voice),
              '--music',str(self.music),'--output',str(self.root/'cli.mp4'),
              '--intervals',str(intervals),'--narration-gain','.8',
              '--attack','.2','--release','.4','--narration-offset','.5','--_worker']
        with (mock.patch.object(sys,'argv',argv),
              mock.patch.object(mixer,'mix',return_value={}) as call,
              mock.patch('builtins.print')):
            mixer.main()
        self.assertEqual(.8,call.call_args.kwargs['narration_gain'])
        self.assertEqual(.2,call.call_args.kwargs['attack'])
        self.assertEqual(.4,call.call_args.kwargs['release'])
        self.assertEqual(.5,call.call_args.kwargs['narration_offset'])

    def test_narration_offset_delays_actual_voice_and_absolute_ducking(self):
        voice=self.root/'offset-voice.wav'
        mixer.run(['ffmpeg','-v','error','-i',str(self.voice),'-t','5.5',str(voice)])
        output=self.root/'offset.mp4'
        receipt=mixer.mix(self.video,voice,self.music,output,[[1.5,2.5],[4.5,5.5]],
                          narration_offset=.5,music_gain=.6,duck_gain=.12)
        values=samples(output)
        self.assertLess(amplitude(values,700,1.1,1.3),.002)
        self.assertGreater(amplitude(values,700,1.7,1.9),.1)
        self.assertLess(amplitude(values,1000,1.7,1.9)/amplitude(values,1000,1.1,1.3),.3)
        self.assertEqual(.5,receipt['narration_offset'])
        self.assertAlmostEqual(6,float(mixer.probe(output)['format']['duration']),places=2)
        for offset,intervals in ((-1,[[1,2]]),(.5,[[0,1]]),(1,[[1,2]])):
            with self.subTest(offset=offset,intervals=intervals),self.assertRaises(ValueError):
                mixer.mix(self.video,voice,self.music,self.root/'bad-offset.mp4',intervals,
                          narration_offset=offset)

    def test_real_cli_managed_worker_completes_once(self):
        intervals=self.root/'managed-cli-intervals.json'
        intervals.write_text('[[1,2],[4,5]]')
        output=self.root/'managed-cli.mp4'
        command=[sys.executable,'-B',mixer.__file__,'--video',str(self.video),
                 '--narration',str(self.voice),'--music',str(self.music),
                 '--output',str(output),'--intervals',str(intervals)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=60)
        self.assertEqual(0,result.returncode,result.stderr+result.stdout)
        self.assertEqual(1,result.stdout.count('"kind": "production-audio-mix/1"'))
        self.assertTrue(output.with_suffix('.mix.json').is_file())

    def test_invalid_envelope_parameters_rejected(self):
        for params in ({'attack':0},{'release':-1},{'attack':float('nan')}, {'release':True}):
            with self.subTest(params=params),self.assertRaises(ValueError):
                mixer.mix(self.video,self.voice,self.music,self.root/'bad-envelope.mp4',[[1,2]],**params)

    def test_source_sound_requires_explicit_choice_and_preserve_keeps_it(self):
        with self.assertRaisesRegex(ValueError,'explicitly preserve or replace'):
            mixer.mix(self.source,self.voice,self.music,self.root/'rejected.mp4',[[1,2]])
        keep = self.root/'preserved.mp4'
        mixer.mix(self.source,self.voice,self.music,keep,[[1,2]],source_audio='preserve')
        self.assertGreater(amplitude(samples(keep),300,2.6,3.0),.1)
        replace = self.root/'replaced.mp4'
        mixer.mix(self.source,self.voice,self.music,replace,[[1,2]],source_audio='replace')
        self.assertLess(amplitude(samples(replace),300,2.6,3.0),.005)

    def test_invalid_intervals_or_music_coverage_rejected(self):
        for intervals in ([],[[2,1]],[[1,3],[2,4]],[[1,7]]):
            with self.subTest(intervals=intervals), self.assertRaises(ValueError):
                mixer.mix(self.video,self.voice,self.music,self.root/'invalid.mp4',intervals)
        short = self.root/'short.wav'
        mixer.run(['ffmpeg','-v','error','-i',str(self.music),'-t','2',str(short)])
        with self.assertRaisesRegex(ValueError,'does not cover'):
            mixer.mix(self.video,self.voice,short,self.root/'short.mp4',[[1,2]])

    def test_shorter_narration_does_not_truncate_picture_or_music(self):
        short = self.root/'short-voice.wav'
        mixer.run(['ffmpeg','-v','error','-i',str(self.voice),'-t','2.2',str(short)])
        output=self.root/'short-voice.mp4'
        mixer.mix(self.video,short,self.music,output,[[1,2]])
        self.assertAlmostEqual(6,float(mixer.probe(output)['format']['duration']),places=2)
        self.assertGreater(amplitude(samples(output),1000,5.3,5.7),.01)

    def test_optional_existing_loudness_normalizer_preserves_video_and_records_command(self):
        output=self.root/'normalized.mp4'
        receipt=mixer.mix(self.video,self.voice,self.music,output,[[1,2],[4,5]],normalize_lufs=-16.)
        self.assertEqual(mixer.video_hash(self.video),mixer.video_hash(output))
        self.assertEqual(2,len(receipt['commands']))
        self.assertIn('loudnorm=I=-16.0:TP=-1.5:LRA=11.0',receipt['commands'][1])
        self.assertIn(str(Path(mixer.__file__).with_name('normalize_loudness.py').resolve()),receipt['inputs'])

    def test_derived_receipt_and_existing_final_review_binding(self):
        from production_timeline import export
        from render_production import verify, check_review, prepare_review
        from production_sound_review import current_plan
        project=self.root/'production-fixture';project.mkdir()
        source=project/'timeline.json'
        source.write_text(json.dumps({'fps':30,'duration':6,'canvas':[160,90],'requires_audio':True,
            'shots':[{'id':'one','start':0,'end':6}],
            'events':[{'id':'point','scene_id':'one','start':0,'end':6,'caption':'测试',
                       'visual':{'type':'test'},'timing_basis':'authored'}]}))
        export(source,project/'derived')
        build=project/'derived/production-build.json'
        # Synthetic FFmpeg fixture, never a claim of an actual HF production run.
        parent=project/'fixture.render.json'
        parent.write_text(json.dumps({'kind':'production-render/1','operation':'test-fixture',
            'output':str(self.source),'output_sha256':mixer.digest(self.source),
            'build_path':str(build),'build_sha256':mixer.digest(build),
            'sound_review_plan_sha256':current_plan(build)[1], 'verification':{'has_audio':True},
            'runtime_roots':[],'runtime_files':{},'host':{'system':platform.system(),
                'release':platform.release(),'machine':platform.machine()},'command':['synthetic-test-fixture']}))
        output=project/'mixed.mp4'
        mixer.mix(self.source,self.voice,self.music,output,[[1,2],[4,5]],source_audio='preserve',parent_receipt=parent)
        derived=output.with_suffix('.render.json')
        receipt=json.loads(derived.read_text())
        self.assertEqual('audio-mix',receipt['operation'])
        self.assertEqual(mixer.digest(parent),receipt['parent_receipt_sha256'])
        self.assertEqual(['synthetic-test-fixture'],receipt['parent_command'])
        self.assertEqual('current_not_reviewed',verify(derived)['status'])
        review=project/'fixture-only-review.json'
        # Deliberate test-only approval fixture, not an authored user review.
        prepare_review(project,output,review)
        fixture=json.loads(review.read_text())
        fixture['approved']=True
        review.write_text(json.dumps(fixture))
        with self.assertRaisesRegex(ValueError,'listening is pending'):
            check_review(project,output,review)
        fixture['audio_review'].update(status='listened',listener='synthetic unit-test assertion only',playback='no real listening claimed')
        fixture['audio_review']['checks']={key:'pass' for key in fixture['audio_review']['checks']}
        for item in fixture['audio_review']['items']:
            item.update(outcome='appropriate',note='synthetic coverage fixture, not an ear judgment')
        review.write_text(json.dumps(fixture))
        self.assertEqual('review_binding_current',check_review(project,output,review)['status'])
        parent.write_text(parent.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'runtime changed'):
            verify(derived)

    def test_input_changed_during_mix_cannot_publish_output_or_receipt(self):
        voice=self.root/'changing.wav';voice.write_bytes(self.voice.read_bytes())
        output=self.root/'changing.mp4'
        original=mixer.run
        def change(command):
            result=original(command)
            if '-filter_complex' in command:
                voice.write_bytes(voice.read_bytes()+b'changed')
            return result
        with mock.patch.object(mixer,'run',side_effect=change),self.assertRaisesRegex(ValueError,'input changed'):
            mixer.mix(self.video,voice,self.music,output,[[1,2]])
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix('.mix.json').exists())


if __name__ == '__main__':
    unittest.main()
