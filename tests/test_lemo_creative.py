"""Intent discovery and malformed-index rejection through the real consumer."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import lemo_reference as lemo
import lemo_creative as creative


class CreativeDiscovery(unittest.TestCase):
    def test_unfamiliar_topic_queries_choose_methods_not_demo_stories(self):
        cases={
            '产品宣传，突出真实操作和结果':'living-screencast',
            '讲清一个关系，让观众逐步理解':'whiteboard',
            '人物史料，展示证据和对比':'archive-lighttable',
            '数据变化，按事件同步声音':'dataviz',
            '对象连续长镜头':'one-line',
            '教学讲解，不要突然切近景，避免快切':'whiteboard',
            'image Skill首发，真实操作和结果':'living-screencast',
        }
        for query,expected in cases.items():
            with self.subTest(query=query):
                result=lemo.search(query)
                self.assertEqual(result['results'][0]['slug'],expected)
                self.assertLessEqual(len(result['results']),3)
                self.assertTrue(result['results'][0]['creative']['mechanism'])
                self.assertTrue(result['results'][0]['matched_terms'])
        self.assertEqual(lemo.search('no-such-reference-xyz')['results'],[])
        self.assertEqual(lemo.search('不要白板')['results'],[])
        self.assertEqual(lemo.search('不要白板，用真实操作演示')['results'][0]['slug'],'living-screencast')
        self.assertNotIn('microscope',[r['slug'] for r in lemo.search('image Skill首发，真实操作和结果')['results']])
        self.assertNotIn('game-show',[r['slug'] for r in lemo.search('教学讲解，不要突然切近景，避免快切')['results']])
        # A life-story reveal is not interchangeable with incremental reasoning.
        self.assertNotIn('one-line',[r['slug'] for r in lemo.search('概念推导，讲清关系，逐步理解')['results']])

    def test_negative_prompt_text_is_not_a_positive_cinema_match(self):
        self.assertEqual(lemo.search('水墨',cinema=True)['results'],[])
        self.assertTrue(lemo.search('工笔',cinema=True)['results'])
        self.assertTrue(lemo.search('Wings',cinema=True)['results'])

    def test_cli_detail_binds_method_to_source_and_evidence_limit(self):
        p=subprocess.run([sys.executable,str(SCRIPTS/'lemo_reference.py'),'inspect','paper-popup'],
                         check=True,capture_output=True,text=True)
        d=json.loads(p.stdout)
        self.assertEqual(d['kind'],'creative-mechanism')
        self.assertTrue(d['refs'])
        self.assertIn('no universal audiovisual quality approval',d['evidence_limit'])
        for slug in ('','../../x','missing'):
            with self.subTest(slug=slug),self.assertRaises(ValueError):creative.inspect(lemo.catalog(),slug)

    def test_actual_search_refuses_empty_stale_duplicate_and_unbound_cards(self):
        source=json.loads(creative.INDEX.read_text())
        variants=[]
        empty=copy.deepcopy(source);empty['styles']=[];variants.append(empty)
        stale=copy.deepcopy(source);stale['catalog_revision']='0'*40;variants.append(stale)
        duplicate=copy.deepcopy(source);duplicate['styles'][1]=duplicate['styles'][0];variants.append(duplicate)
        missing=copy.deepcopy(source);missing['styles'][0]['mechanism']='';variants.append(missing)
        wrong=copy.deepcopy(source);wrong['styles'][0]['refs']=['other/STYLE.md:1'];variants.append(wrong)
        invented=copy.deepcopy(source)
        invented['styles'][0]['refs']=[f"styles/{invented['styles'][0]['slug']}/invented.py:1"]
        variants.append(invented)
        zero_line=copy.deepcopy(source)
        zero_line['styles'][0]['refs']=[zero_line['styles'][0]['refs'][0].rsplit(':',1)[0]+':0']
        variants.append(zero_line)
        no_evidence=copy.deepcopy(source);no_evidence['basis']='';variants.append(no_evidence)
        no_research=copy.deepcopy(source);no_research['research_revision']='';variants.append(no_research)
        wrong_research=copy.deepcopy(source);wrong_research['research_revision']='0'*40;variants.append(wrong_research)
        missing_line=copy.deepcopy(source)
        missing_line['styles'][0]['refs']=[missing_line['styles'][0]['refs'][0].rsplit(':',1)[0]+':999999999']
        variants.append(missing_line)
        malformed=copy.deepcopy(source);malformed['styles'][0]=None;variants.append(malformed)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'index.json'
            for bad in variants:
                p.write_text(json.dumps(bad))
                with self.subTest(kind=bad.get('catalog_revision')),patch.object(creative,'INDEX',p),self.assertRaises(ValueError):
                    lemo.search('白板')
        for query in ('',' ',None):
            with self.subTest(query=query),self.assertRaises(ValueError):lemo.search(query)

    def test_source_binding_file_corruption_is_not_silently_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sources.json';p.write_text('{}')
            with patch.object(creative,'SOURCES',p),self.assertRaisesRegex(ValueError,'fingerprint'):
                lemo.search('白板')


if __name__=='__main__':unittest.main()
