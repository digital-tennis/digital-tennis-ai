import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('match_report', Path(__file__).resolve().parents[1]/'tools/evaluate-match-report.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class MatchReportTests(unittest.TestCase):
    def report(self):
        return dict(schema=1, passed=True, scope='fixture only', modelSha256='a'*64, gameplayHash='b'*64,
                    cases=[dict(difficulty=d, seed=s, near='KOR', far='JPN', points=8, nearPoints=4, farPoints=4, nearHits=2, aiHits=2,
                                aiAttempts=3, aiRejected=1, humanServes=4, aiServes=4, learnedDecisions=3, actions=[1, 1, 0, 0, 0, 1])
                           for d in module.LEVELS for s in module.SEEDS])
    def test_aggregates_real_counts_without_claiming_human_win_rate(self):
        result=module.summarize(self.report())
        self.assertEqual(result['results'][0]['points'],24)
        self.assertEqual(result['results'][0]['scriptedPointShare'],.5)
        self.assertEqual(result['results'][0]['actions'],[3,3,0,0,0,3])
    def test_rejects_partial_duplicate_tampered_and_inactive_runs(self):
        for change in ('incomplete','duplicate','points','actions','inactive','negative','boolean','hash','roster'):
            with self.subTest(change=change):
                report=self.report();r=report['cases'][0]
                if change=='incomplete':report['passed']=False
                if change=='duplicate':report['cases'][1]=copy.deepcopy(r)
                if change=='points':r['points']+=1
                if change=='actions':r['actions'][0]+=1
                if change=='inactive':r['aiServes']=0
                if change=='negative':r['aiRejected']=-1
                if change=='boolean':r['aiHits']=True
                if change=='roster':r['far']='ESP'
                if change=='hash':report['modelSha256']='bad'
                with self.assertRaises(ValueError):module.summarize(report)

if __name__=='__main__':unittest.main()
