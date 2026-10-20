"""Checkpoint fault injection and deterministic PPO continuation (no Unity claims)."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import pickle
import random
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import PPO

SPEC=importlib.util.spec_from_file_location('complete_checkpoint',Path(__file__).resolve().parents[1]/'Training/checkpoint.py')
cp=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(cp)

class ConstantEnv(gym.Env):
    def __init__(self):
        self.observation_space=gym.spaces.Box(-1,1,(2,),dtype=np.float32);self.action_space=gym.spaces.Discrete(2);self.t=0
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed);self.t=0;return np.zeros(2,np.float32),{}
    def step(self,a):
        self.t+=1
        return np.array([self.t%3/3,0],np.float32),float(a==self.t%2),False,False,{}

class Checkpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):torch.set_num_threads(1)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()/'checkpoints'
        self.env=ConstantEnv();self.model=PPO('MlpPolicy',self.env,n_steps=32,batch_size=16,n_epochs=2,seed=9,device='cpu',policy_kwargs={'net_arch':[8]})
        self.model.learn(32);self.contract={'schema':1,'config':'abc','environment':'Unity source hash','normalization':'fixed'}
    def tearDown(self):self.tmp.cleanup()
    def save(self):return cp.save(self.root,self.model,{'counter':32},self.contract,[])
    def test_corruption_rejected_before_deserialization(self):
        name=self.save();path=self.root/name
        with zipfile.ZipFile(path) as z:payload={n:z.read(n) for n in z.namelist()}
        payload['state.pkl']=b'corrupted'
        with zipfile.ZipFile(path,'w') as z:
            for n,b in payload.items():z.writestr(n,b)
        with patch.object(cp.pickle,'loads',side_effect=AssertionError('must not deserialize')):
            with self.assertRaisesRegex(ValueError,'corruption'):cp.read(self.root,self.contract)
    def test_config_schema_environment_and_normalization_mismatch(self):
        self.save()
        for key in self.contract:
            bad=dict(self.contract);bad[key]='changed'
            with self.assertRaisesRegex(ValueError,'mismatch'):cp.read(self.root,bad)
    def test_unsafe_pointer_archive_and_symlink_rejected(self):
        self.save();ptr=self.root/'current.json';original=ptr.read_bytes()
        for name in ('../../escape.zip','/tmp/escape.zip','x.zip',None):
            ptr.write_text(json.dumps({'current':name,'previous':None}))
            with self.assertRaises(ValueError):cp.read(self.root,self.contract)
        ptr.write_bytes(original)
        alias=Path(self.tmp.name)/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):cp.read(alias,self.contract)
        with self.assertRaises(ValueError):cp.save(self.root/'..'/'outside',self.model,{},self.contract,[])
        name=json.loads(ptr.read_text())['current']
        with zipfile.ZipFile(self.root/name,'a') as z:z.writestr('../escape',b'unsafe')
        with self.assertRaisesRegex(ValueError,'Unsafe archive'):cp.read(self.root,self.contract)
    def test_nonfinite_weights_optimizer_and_shape_are_rejected(self):
        original=copy.deepcopy(self.model.policy.state_dict())
        with torch.no_grad():next(self.model.policy.parameters()).fill_(float('nan'))
        with self.assertRaisesRegex(ValueError,'Nonfinite'):self.save()
        self.model.policy.load_state_dict(original)
        with self.assertRaisesRegex(ValueError,'observation shape'):cp.save(self.root,self.model,{},dict(self.contract,inputSize=32),[])
        with self.assertRaisesRegex(ValueError,'action shape'):cp.save(self.root,self.model,{},dict(self.contract,actionCount=6),[])
        optimizer_state=next(iter(self.model.policy.optimizer.state.values()))
        optimizer_state['exp_avg'].fill_(float('nan'))
        with self.assertRaisesRegex(ValueError,'Nonfinite'):self.save()
    def test_symlink_pointer_cannot_replace_a_committed_checkpoint(self):
        self.save();ptr=self.root/'current.json';safe=ptr.read_bytes()
        external=Path(self.tmp.name)/'external.json';external.write_bytes(safe)
        ptr.unlink();ptr.symlink_to(external)
        with self.assertRaisesRegex(ValueError,'Unsafe pointer'):self.save()
        with self.assertRaisesRegex(ValueError,'Unsafe pointer'):cp.read(self.root,self.contract)
        self.assertEqual(external.read_bytes(),safe)
    def test_header_schema_and_truncated_archive_are_rejected(self):
        name=self.save();path=self.root/name
        with zipfile.ZipFile(path) as z:payload={n:z.read(n) for n in z.namelist()}
        manifest=json.loads(payload['manifest.json']);manifest['schema']=99
        with zipfile.ZipFile(path,'w') as z:
            for k,v in payload.items():z.writestr(k,json.dumps(manifest) if k=='manifest.json' else v)
        with self.assertRaisesRegex(ValueError,'mismatch'):cp.read(self.root,self.contract)
        # A truncated generation cannot be selected implicitly as a fresh model.
        path.write_bytes(b'PK truncated')
        with self.assertRaises(zipfile.BadZipFile):cp.read(self.root,self.contract)
    def test_interrupted_write_preserves_previous_committed_generation(self):
        first=self.save();before=(self.root/'current.json').read_bytes()
        real_replace=cp.os.replace
        def fail_pointer(src,dst):
            if str(dst).endswith('current.json'):raise OSError('injected disk failure')
            return real_replace(src,dst)
        with patch.object(cp.os,'replace',side_effect=fail_pointer):
            with self.assertRaises(OSError):self.save()
        self.assertEqual(before,(self.root/'current.json').read_bytes());cp.read(self.root,self.contract)
        second=self.save();self.assertNotEqual(first,second)
        (self.root/second).write_bytes(b'broken archive')
        with self.assertRaises(zipfile.BadZipFile):cp.read(self.root,self.contract)
        m,data=cp.read(self.root,self.contract,previous=True)
        self.assertEqual(pickle.loads(data['state.pkl'])['state']['counter'],32)
    def test_lease_or_world_mismatch_rejected_without_model_load(self):
        class Lease:
            lease='new'
            def request(self,_):return {'tick':8}
        cp.save(self.root,self.model,{'lease':'old','environment':{'last':{'tick':8}}},self.contract,[])
        with patch.object(cp.PPO,'load',side_effect=AssertionError('must not load')):
            with self.assertRaisesRegex(ValueError,'lease/state mismatch'):cp.load(self.root,Lease(),self.contract,self.root/'pool')
        cp.save(self.root,self.model,{'lease':'new','environment':{'last':{'tick':7}}},self.contract,[])
        with self.assertRaisesRegex(ValueError,'lease/state mismatch'):cp.load(self.root,Lease(),self.contract,self.root/'pool')
    def test_uninterrupted_and_resumed_optimizer_weights_rng_and_counters_are_identical(self):
        initial_t=self.env.t
        cp.save(self.root,self.model,{'counter':self.model.num_timesteps,'monitor':{k:copy.deepcopy(getattr(self.model.get_env().envs[0],k)) for k in cp.MONITOR_KEYS}},self.contract,[])
        self.model.learn(64,reset_num_timesteps=False)
        expected_opt=cp.optimizer_hash(self.model)
        expected={k:v.clone() for k,v in self.model.policy.state_dict().items()}
        expected_rng=(random.random(),np.random.random(),torch.rand(()).item())
        m,payload=cp.read(self.root,self.contract);saved=pickle.loads(payload['state.pkl'])
        self.env.t=initial_t
        resumed=PPO.load(io.BytesIO(payload['model.zip']),env=self.env,device='cpu',force_reset=False)
        for k,v in saved['state']['monitor'].items():setattr(resumed.get_env().envs[0],k,v)
        cp.restore_rng(saved['rng']);resumed.learn(64,reset_num_timesteps=False)
        self.assertEqual(resumed.num_timesteps,96);self.assertEqual(resumed._n_updates,self.model._n_updates)
        self.assertEqual(cp.optimizer_hash(resumed),expected_opt)
        for k,v in resumed.policy.state_dict().items():self.assertTrue(torch.equal(v,expected[k]),k)
        self.assertEqual(expected_rng,(random.random(),np.random.random(),torch.rand(()).item()))

if __name__=='__main__':unittest.main()
