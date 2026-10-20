"""Real FFmpeg regressions; run through a single host resource slot when available.

All fixtures/output live under TemporaryDirectory outside Skill scanning trees.
Audio checks measure tone identity and boundary energy; they do not claim listening.
"""
from pathlib import Path
import array
import importlib.util
import json
import math
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'assemble_edl.py'
spec = importlib.util.spec_from_file_location('assemble_edl_under_test', SCRIPT)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def ff(*args):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', *map(str, args)],
                            capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.decode()[-3000:])
    return result.stdout


class RealAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='video-edl-tests-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        # One source changes pitch halfway through, making discarded intervals observable.
        ff('-f', 'lavfi', '-i', 'color=c=red:s=320x180:r=30:d=2',
           '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=1',
           '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000:duration=1',
           '-filter_complex', '[1:a][2:a]concat=n=2:v=0:a=1[a]',
           '-map', '0:v', '-map', '[a]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', cls.root/'red.mp4')
        ff('-f', 'lavfi', '-i', 'color=c=blue:s=320x180:r=30:d=2',
           '-f', 'lavfi', '-i', 'sine=frequency=660:sample_rate=48000:duration=2',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', cls.root/'blue.mp4')
        ff('-i', cls.root/'blue.mp4', '-c:v', 'copy', '-an', cls.root/'silent.mp4')
        ff('-i', cls.root/'blue.mp4', '-vf', 'scale=180:320', '-c:a', 'copy', cls.root/'portrait.mp4')
        ff('-i', cls.root/'blue.mp4', '-f', 'lavfi', '-i', 'sine=frequency=660:sample_rate=48000:duration=0.3',
           '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', cls.root/'short-audio.mp4')
        for name, duration in [('exact',1),('padding',1.02),('near-short',.98),('short',.9),('long',1.1)]:
            ff('-f', 'lavfi', '-i', f'sine=frequency=990:sample_rate=48000:duration={duration}',
               cls.root/f'{name}.wav')
        print('test FFmpeg: '+subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.root))

    def edl(self, clips=None, audio=None):
        clips = clips or [('red.mp4',.2,.6),('blue.mp4',.2,.8)]
        scenes=[]; cursor=0
        for name, start, end in clips:
            scenes.append(dict(source=str(self.root/name), source_in=start, source_out=end,
                               timeline_start=cursor,timeline_end=cursor+end-start))
            cursor += end-start
        data={'metadata':{'fps':30,'total_duration':cursor},'scenes':scenes}
        if audio:
            data['audio_file']=str(self.root/audio)
        path=self.case/'edl.json';path.write_text(json.dumps(data));return str(path)

    def output(self, name='result.mp4'):
        return str(self.case/name)

    def samples(self, path):
        raw=ff('-i', path, '-map', '0:a:0', '-ac', '1', '-ar', '48000', '-f','f32le','-')
        values=array.array('f');values.frombytes(raw);return values

    def tone(self, values, start, expected):
        data=values[round(start*48000):round((start+.1)*48000)]
        energies={f:abs(sum(v*complex(math.cos(2*math.pi*f*i/48000),
                                      math.sin(2*math.pi*f*i/48000)) for i,v in enumerate(data)))
                  for f in (440,660,880,990)}
        self.assertEqual(max(energies,key=energies.get),expected,energies)

    def continuous(self, values, duration):
        # A zero-filled splice or AAC packet gap cannot pass this boundary energy check.
        for start in range(960,round(duration*48000)-960,960):
            chunk=values[start:start+960]
            self.assertGreater(math.sqrt(sum(v*v for v in chunk)/len(chunk)),.02, start/48000)

    def test_source_cut_preserves_audio_and_landscape(self):
        out=a.assemble(self.edl([('red.mp4',.2,.6),('red.mp4',1.2,1.8)]),
                       output_path=self.output(),audio_mode='source')
        video=a._one_stream(a._probe(out),'video')
        self.assertEqual((video['width'],video['height']),(320,180))
        sound=self.samples(out);self.tone(sound,.15,440);self.tone(sound,.65,880)
        self.continuous(sound,1)
        self.assertAlmostEqual(len(sound)/48000,1,delta=a._timing_tolerance(30))

    def test_reorder_distinct_sources_preserves_audio_picture_pair(self):
        out=a.assemble(self.edl([('blue.mp4',.2,.6),('red.mp4',1.2,1.8)]),
                       output_path=self.output(),audio_mode='source',width=640,height=360)
        sound=self.samples(out);self.tone(sound,.15,660);self.tone(sound,.65,880)
        self.continuous(sound,1)
        for t,channel in [(.2,2),(.7,0)]:
            pixel=ff('-ss',t,'-i',out,'-vf','scale=1:1','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-')
            self.assertEqual(max(range(3),key=lambda c:pixel[c]),channel)

    def test_24fps_fractional_second_cuts_keep_exact_frame_clock(self):
        # Millisecond intermediate timestamps cannot represent 1/24 seconds.
        # These cuts exercise the consumer's final exact-FPS/frame-count gate.
        out=a.assemble(self.edl([('blue.mp4',.125,.125+31/24),
                                ('red.mp4',.125,.125+28/24)]),
                       output_path=self.output(),audio_mode='source',fps=24)
        video=a._one_stream(a._probe(out,True),'video')
        self.assertEqual(video['avg_frame_rate'],'24/1')
        self.assertEqual(int(video['nb_read_frames']),59)
        self.assertAlmostEqual(a._duration(video),59/24,delta=1e-6)
        sound=self.samples(out)
        self.tone(sound,.2,660);self.tone(sound,1.5,440)
        self.continuous(sound,59/24)

    def test_silent_intent_removes_audio_keeps_original_canvas(self):
        out=a.assemble(self.edl(),output_path=self.output(),audio_mode='silent')
        self.assertEqual(a._streams(a._probe(out),'audio'),[])
        self.assertEqual(a._one_stream(a._probe(out),'video')['width'],320)

    def test_external_legacy_default_and_small_padding(self):
        for name in ('exact','padding','near-short'):
            out=a.assemble(self.edl(audio=f'{name}.wav'),output_path=self.output(name+'.mp4'))
            video=a._one_stream(a._probe(out),'video')
            self.assertEqual((video['width'],video['height']),(1080,1920))
            self.tone(self.samples(out),.2,990)
            self.assertEqual(int(a._one_stream(a._probe(out,True),'video')['nb_read_frames']),30)

    def test_external_short_long_rejected_without_shortest(self):
        for name in ('short','long'):
            with self.assertRaisesRegex(ValueError,'external audio duration.*tolerance='):
                a.assemble(self.edl(audio=f'{name}.wav'),output_path=self.output(name+'.mp4'))
            self.assertFalse(Path(self.output(name+'.mp4')).exists())

    def test_missing_audio_and_conflicting_intent_fail(self):
        with self.assertRaisesRegex(ValueError,'exactly one audio'):
            a.assemble(self.edl([('silent.mp4',.2,1.2)]),output_path=self.output(),audio_mode='source')
        for mode in ('source','silent'):
            with self.assertRaisesRegex(ValueError,'conflicts'):
                a.assemble(self.edl(audio='exact.wav'),output_path=self.output(),audio_mode=mode)
        with self.assertRaisesRegex(ValueError,'declare --audio-mode'):
            a.assemble(self.edl(),output_path=self.output())

    def test_empty_bounds_dimensions_and_existing_output_fail(self):
        empty=self.case/'empty.json';empty.write_text('{"scenes":[]}')
        with self.assertRaisesRegex(ValueError,'no scenes'):
            a.assemble(str(empty),output_path=self.output(),audio_mode='silent')
        with self.assertRaisesRegex(ValueError,'exceeds video'):
            a.assemble(self.edl([('red.mp4',.2,2.2)]),output_path=self.output(),audio_mode='source')
        with self.assertRaisesRegex(ValueError,'mixed source dimensions'):
            a.assemble(self.edl([('red.mp4',.2,.6),('portrait.mp4',.2,.8)]),output_path=self.output(),audio_mode='source')
        Path(self.output()).write_bytes(b'existing-deliverable')
        with self.assertRaisesRegex(ValueError,'output already exists'):
            a.assemble(self.edl(),output_path=self.output(),audio_mode='silent')
        self.assertEqual(Path(self.output()).read_bytes(),b'existing-deliverable')

    def test_final_gate_rejects_actual_audio_loss_mutation(self):
        original=a._finish_audio
        def lose_audio(video,audio,out,mode):
            original(video,audio,out,'silent')
        with patch.object(a,'_finish_audio',side_effect=lose_audio):
            with self.assertRaisesRegex(ValueError,'audio streams do not match'):
                a.assemble(self.edl(),output_path=self.output(),audio_mode='source')
        self.assertFalse(Path(self.output()).exists())

    def test_source_audio_coverage_and_original_order_gate(self):
        with self.assertRaisesRegex(ValueError,'source audio does not cover'):
            a.assemble(self.edl([('short-audio.mp4',.2,1.2)]),output_path=self.output(),audio_mode='source')
        with self.assertRaises(SystemExit) as failure:
            a.assemble(self.edl([('red.mp4',.8,1.2),('red.mp4',.2,.8)]),
                       output_path=self.output(),audio_mode='source')
        self.assertEqual(failure.exception.code,2)

    def test_final_gate_rejects_real_truncated_video_mutation(self):
        def truncate(video,audio,out,mode):
            ff('-i',video,'-t','0.6','-map','0:v','-map','0:a',
               '-c:v','libx264','-c:a','aac',out)
        with patch.object(a,'_finish_audio',side_effect=truncate):
            with self.assertRaisesRegex(ValueError,'frame count differs'):
                a.assemble(self.edl(),output_path=self.output(),audio_mode='source')
        self.assertFalse(Path(self.output()).exists())

    def test_cli_source_and_silent(self):
        for mode in ('source','silent'):
            proc=subprocess.run(['python3','-B',str(SCRIPT),self.edl(),'--audio-mode',mode,
                                 '--width','320','--height','180','--out',self.output(mode+'.mp4')],
                                capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)


if __name__=='__main__':
    unittest.main(verbosity=2)
