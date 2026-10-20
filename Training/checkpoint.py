"""Atomic trusted-local PPO checkpoints. Unity is a suspended live environment lease.

The synchronous bridge cannot advance between requests. A checkpoint restores all
Python state and requires that same lease and exact Unity state; it never resets a
lost/nonmatching world. Pickle payloads must only come from this local writer.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import pickle
import random
import re
import uuid
import zipfile

import numpy as np
import torch
from stable_baselines3 import PPO

MONITOR_KEYS=('needs_reset','rewards','episode_returns','episode_lengths','episode_times','total_steps','current_reset_info','t_start')

NAME = re.compile(r'^[a-f0-9]{32}\.zip$')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return digest(pickle.dumps(value, protocol=5))


def optimizer_hash(model):
    # Pickle's tensor storage identities are unstable; hash tensor values recursively.
    def plain(x):
        if isinstance(x, torch.Tensor):
            a=x.detach().cpu().numpy()
            return (str(a.dtype), a.shape, a.tobytes())
        if isinstance(x, dict):return [(k,plain(v)) for k,v in sorted(x.items(),key=lambda kv:str(kv[0]))]
        if isinstance(x, (tuple,list)):return [plain(v) for v in x]
        return x
    return fingerprint(plain(model.policy.optimizer.state_dict()))


def validate_model(model,contract):
    def check(value):
        if isinstance(value,torch.Tensor) and not torch.isfinite(value).all():raise ValueError('Nonfinite model/optimizer')
        if isinstance(value,dict):
            for v in value.values():check(v)
        if isinstance(value,(tuple,list)):
            for v in value:check(v)
    check(model.policy.state_dict());check(model.policy.optimizer.state_dict())
    if 'inputSize' in contract and model.observation_space.shape!=(contract['inputSize'],):raise ValueError('Checkpoint observation shape')
    if 'actionCount' in contract and model.action_space.n!=contract['actionCount']:raise ValueError('Checkpoint action shape')


def rng_state():
    return dict(python=random.getstate(),numpy=np.random.get_state(),torch=torch.get_rng_state())


def restore_rng(s):
    random.setstate(s['python']);np.random.set_state(s['numpy']);torch.set_rng_state(s['torch'])


def safe_root(root):
    root=Path(root)
    if '..' in root.parts:raise ValueError('Unsafe checkpoint path')
    for p in (root,*root.parents):
        if p.is_symlink():raise ValueError('Symlink checkpoint path')
    root.mkdir(parents=True,exist_ok=True)
    return root


def sync_write(path,data):
    with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())


def save(root,model,state,contract,pool):
    """Immutable generation first, atomic current pointer last; retain previous generation."""
    root=safe_root(root)
    validate_model(model,contract)
    buf=io.BytesIO();model.save(buf)
    payload={'model.zip':buf.getvalue(),'state.pkl':pickle.dumps(dict(state=state,rng=rng_state()),protocol=5)}
    for i,actor in enumerate(pool):
        actor.verify();payload[f'pool/{i}.json']=actor.path.read_bytes()
    manifest=dict(schema=1,contract=contract,files={k:digest(v) for k,v in payload.items()},poolCount=len(pool))
    generation=uuid.uuid4().hex+'.zip';temp=root/(generation+'.tmp')
    try:
        with temp.open('xb') as f:
            with zipfile.ZipFile(f,'w',compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifest.json',json.dumps(manifest,sort_keys=True))
                for k,v in payload.items():z.writestr(k,v)
            f.flush();os.fsync(f.fileno())
        os.replace(temp,root/generation)
        pointer=root/'current.json';previous=None
        if pointer.is_symlink():raise ValueError('Unsafe pointer')
        if pointer.exists():
            old=json.loads(pointer.read_text());previous=old['current']
        ptr=root/(generation+'.pointer')
        sync_write(ptr,json.dumps(dict(current=generation,previous=previous)).encode())
        os.replace(ptr,pointer)
        fd=os.open(root,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temp.unlink(missing_ok=True)
    return generation


def read(root,contract,previous=False):
    root=safe_root(root);ptr=root/'current.json'
    if ptr.is_symlink():raise ValueError('Unsafe pointer')
    p=json.loads(ptr.read_text());name=p['previous' if previous else 'current']
    if not isinstance(name,str) or not NAME.fullmatch(name):raise ValueError('Unsafe generation')
    path=root/name
    if path.is_symlink():raise ValueError('Unsafe generation')
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or 'manifest.json' not in names:raise ValueError('Invalid archive entries')
        m=json.loads(z.read('manifest.json'))
        if m.get('schema')!=1 or m.get('contract')!=contract:raise ValueError('Checkpoint schema/config/environment mismatch')
        allowed={'model.zip','state.pkl'}|{f'pool/{i}.json' for i in range(m['poolCount'])}
        if set(m['files'])!=allowed or set(names)!=allowed|{'manifest.json'}:raise ValueError('Unsafe archive paths')
        payload={k:z.read(k) for k in allowed}
        if any(digest(v)!=m['files'][k] for k,v in payload.items()):raise ValueError('Checkpoint corruption')
    return m,payload


def load(root,env,contract,pool_dir,previous=False):
    # Validate all bytes and the live world BEFORE deserialization or any model mutation.
    m,payload=read(root,contract,previous)
    s=pickle.loads(payload['state.pkl']);state=s['state']
    if env.lease!=state['lease'] or env.request({'op':'checkpoint'})!=state['environment']['last']:
        raise ValueError('Unity environment lease/state mismatch; refusing reset')
    from self_play import Actor
    pool_dir=Path(pool_dir);pool_dir.mkdir(parents=True,exist_ok=True);actors=[]
    for i in range(m['poolCount']):
        data=payload[f'pool/{i}.json'];path=pool_dir/(digest(data)+'.json')
        if path.exists() and path.read_bytes()!=data:raise ValueError('Pool collision')
        if not path.exists():sync_write(path,data)
        actors.append(Actor(path))
    model=PPO.load(io.BytesIO(payload['model.zip']),env=env,device='cpu',force_reset=False)
    validate_model(model,contract)
    if model.num_timesteps!=state['globalStep'] or model._n_updates!=state['updates'] or optimizer_hash(model)!=state['optimizerSha256']:
        raise ValueError('Optimizer/counter restoration mismatch')
    for key,value in state['environment'].items():setattr(env,key,copy.deepcopy(value))
    env.pool=actors;env.opponent=actors[state['opponentIndex']]
    for g,rs in zip(env.rng,state['sideRng']):g.bit_generator.state=rs
    for target,rs in zip((env,env.action_space,env.observation_space),state['gymRng']):
        if rs is not None:
            target._np_random=np.random.default_rng();target._np_random.bit_generator.state=rs
    vec=model.get_env()
    for key,value in state['vector'].items():setattr(vec,key,copy.deepcopy(value))
    for key,value in state['monitor'].items():setattr(vec.envs[0],key,copy.deepcopy(value))
    restore_rng(s['rng'])
    return model,state


def capture(model,env,snapshots):
    if model.rollout_buffer.pos!=model.n_steps or not model.rollout_buffer.full:raise ValueError('Checkpoint requires completed rollout/update boundary')
    last=env.request({'op':'checkpoint'})
    if last!=env.last:raise ValueError('Unity advanced outside bridge')
    keys=('base_seed','episode','steps','episodes','current','last','start_step','total_reward','schedule','side','kind','eval_case')
    vec=model.get_env()
    return dict(lease=env.lease,globalStep=model.num_timesteps,updates=model._n_updates,optimizerSha256=optimizer_hash(model),
        environment={k:copy.deepcopy(getattr(env,k)) for k in keys},sideRng=[copy.deepcopy(g.bit_generator.state) for g in env.rng],
        gymRng=[copy.deepcopy(x._np_random.bit_generator.state) if getattr(x,'_np_random',None) is not None else None for x in (env,env.action_space,env.observation_space)],
        opponentIndex=env.pool.index(env.opponent),snapshots=copy.deepcopy(snapshots),
        monitor={k:copy.deepcopy(getattr(vec.envs[0],k)) for k in MONITOR_KEYS},
        vector={k:copy.deepcopy(getattr(vec,k)) for k in ('buf_obs','buf_dones','buf_rews','buf_infos','reset_infos')},
        normalization=dict(kind='fixed Unity observation v2',clip=[-2,2],runningStatistics=None),rolloutBoundary='fully optimized; no pending gradients/transitions')
