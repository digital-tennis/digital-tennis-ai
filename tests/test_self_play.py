"""Fault-injection tests, never used as evidence of real matches."""
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Training'))
import self_play as sp

class SelfPlayContract(unittest.TestCase):
    def test_configuration_rejects_missing_duplicate_nonfinite_fraction_and_small_budget(self):
        p=Path(sp.__file__).with_name('self-play.csv');original=p.read_text()
        self.assertEqual(sp.settings(p)['steps'],32768)
        for text in [original+'steps,32768\n',original.replace('32768','nan'),original.replace('32768','32768.5'),original.replace('32768','16384'),original.replace('8192','8193'),original.replace('evaluation_seed','unknown')]:
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'s.csv';path.write_text(text)
                with self.assertRaises(ValueError):sp.settings(path)
    def test_nonterminal_reset_rejected(self):
        env=object.__new__(sp.Duel);env.last={'done':False}
        with self.assertRaises(RuntimeError):env.reset()
    def test_frozen_actor_deterministic_validates_and_detects_modification(self):
        source=Path(sp.__file__).resolve().parents[1]/'Runtime/Resources/DigitalTennisAI/full-match-ppo.json'
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'actor.json';path.write_bytes(source.read_bytes());actor=sp.Actor(path);o=np.zeros(32,np.float32)
            a=actor.predict(o);self.assertEqual(a,actor.predict(o));actor.verify()
            for bad in (np.zeros(31),np.full(32,np.nan),np.full(32,3)):
                with self.assertRaises(ValueError):actor.predict(bad)
            path.write_text('{}')
            with self.assertRaises(ValueError):actor.verify()
    def test_separate_side_random_streams(self):
        near=np.random.default_rng(17);far=np.random.default_rng(7936);reference=np.random.default_rng(7936)
        near.integers(6,size=1000)
        np.testing.assert_array_equal(far.integers(6,size=100),reference.integers(6,size=100))
if __name__=='__main__':unittest.main()
