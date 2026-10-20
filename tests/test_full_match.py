"""Contract tests use mocks only for fault injection, never as match evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('full_match',ROOT/'Training/full_match.py');fm=importlib.util.module_from_spec(spec);spec.loader.exec_module(fm)
class Contract(unittest.TestCase):
 def test_default_config_and_learning_horizon(self):
  c=fm.config(ROOT/'Training/full-match.csv');self.assertEqual(c['steps'],65536);self.assertGreater(c['gamma'],.9);self.assertGreaterEqual(c['steps']//c['n_steps'],4)
 def test_all_config_fields_validate_nonfinite_unknown_duplicate_range_integer(self):
  original=(ROOT/'Training/full-match.csv').read_text()
  candidates=[original+'seed,2\n',original.replace('seed,20261021','oops,2'),original.replace('gamma,0.995','gamma,nan'),original.replace('n_steps,2048','n_steps,2048.5'),original.replace('reward_match,10','reward_match,-1'),original.replace('batch_size,128','batch_size,127')]
  for text in candidates:
   with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'c.csv';p.write_text(text)
    with self.assertRaises(ValueError):fm.config(p)
 def test_normalization_and_boundary_clamp(self):
  np.testing.assert_array_equal(fm.normalize(fm.SCALES),np.ones(32));np.testing.assert_array_equal(fm.normalize(-fm.SCALES*3),-np.ones(32)*2)
  for bad in [np.zeros(31),np.full(32,np.nan),np.full(32,np.inf)]:
   with self.assertRaises(ValueError):fm.normalize(bad)
 def test_gym_rejects_reset_of_incomplete_match(self):
  env=object.__new__(fm.UnityMatch);env.last={'done':False}
  with self.assertRaises(RuntimeError):env.reset()
 def test_actions_shape_and_limits(self):
  env=object.__new__(fm.UnityMatch);env.action_space=fm.gym.spaces.Discrete(6)
  for a in [-1,6,np.nan]:
   with self.assertRaises(ValueError):env.step(a)
if __name__=='__main__':unittest.main()
