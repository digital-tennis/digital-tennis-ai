"""Gymnasium/PPO over a stepped actual Unity scene. No Python physics or scoring."""
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import socket
import time
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[1]/'.work/plot-cache'))
import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback

SCALES=np.array([4.115,4,11.885,30,30,30,4.115,11.885,4.115,11.885,2,30,7,7,6,6,2,2,1,1,4,2,100,100,3,3,10,10,14,14,1,2],dtype=np.float32)
SCHEMA={'steps':(65536,10000000,True),'seed':(1,2147483000,True),'n_steps':(128,32768,True),'batch_size':(8,32768,True),'n_epochs':(1,20,True),
 'learning_rate':(1e-7,.01,False),'gamma':(.9,.99999,False),'gae_lambda':(.8,1,False),'clip_range':(.01,.4,False),
 'ent_coef':(0,.2,False),'vf_coef':(0,1,False),'max_grad_norm':(.01,10,False),'reward_point':(0,10,False),'reward_game':(0,20,False),
 'reward_set':(0,50,False),'reward_match':(0,100,False),'reward_rejected':(-1,0,False)}

def config(path):
    with Path(path).open() as f: rows=list(csv.DictReader(f))
    if len(rows)!=len(SCHEMA) or {r['key'] for r in rows}!=set(SCHEMA): raise ValueError('CSV missing/duplicate/unknown key')
    out={}
    for r in rows:
        v=float(r['value']);lo,hi,integer=SCHEMA[r['key']]
        if not math.isfinite(v) or not lo<=v<=hi or integer and not v.is_integer():raise ValueError('CSV range/type: '+r['key'])
        out[r['key']]=int(v) if integer else v
    if out['n_steps']%out['batch_size'] or out['steps']%out['n_steps'] or out['steps']//out['n_steps']<4:raise ValueError('CSV rollout/batch/update budget')
    return out

def normalize(raw):
    raw=np.asarray(raw,dtype=np.float32)
    if raw.shape!=(32,) or not np.isfinite(raw).all():raise ValueError('Observation shape/finite')
    return np.clip(raw/SCALES,-2,2)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def weights_hash(model):
    h=hashlib.sha256()
    for k,v in sorted(model.policy.state_dict().items()):h.update(k.encode());h.update(v.detach().cpu().numpy().tobytes())
    return h.hexdigest()

class UnityMatch(gym.Env):
    metadata={'render_modes':[]}
    def __init__(self,port,cfg,evidence):
        self.cfg=cfg;self.base_seed=cfg['seed'];self.episode=0;self.steps=0;self.episodes=[];self.current=None;self.last=None
        self.observation_space=gym.spaces.Box(-2,2,(32,),dtype=np.float32);self.action_space=gym.spaces.Discrete(6)
        deadline=time.monotonic()+240
        while True:
            try:self.sock=socket.create_connection(('127.0.0.1',port),timeout=5);break
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.25)
        self.sock.settimeout(600);self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        self.wire=self.sock.makefile('rwb');self.raw=Path(evidence).open('w');self.start_step=0
    def request(self,data):
        self.wire.write((json.dumps(data,separators=(',',':'))+'\n').encode());self.wire.flush()
        line=self.wire.readline()
        if not line:raise RuntimeError('Unity bridge disconnected')
        result=json.loads(line)
        if data['op']=='close':return result
        if [result[k] for k in ('observationVersion','actionVersion','rewardVersion')]!=[2,1,1] or result['rules']!=[3,6,6,7]:raise ValueError('Bridge protocol/default rules')
        o=np.asarray(result['observation'],dtype=np.float32)
        if not self.observation_space.contains(o):raise ValueError('Bridge observation shape/range/finite')
        if result['attempts']!=result['hits']+result['rejected']:raise ValueError('Dishonest gate counters')
        return result
    def record(self,kind,state):
        self.raw.write(json.dumps(dict(kind=kind,step=self.steps,episode=self.episode,state=state),separators=(',',':'))+'\n');self.raw.flush()
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        if self.last is not None and not self.last['done']:raise RuntimeError('Cannot truncate a real match')
        self.episode+=1;idx=(self.episode-1)%15
        self.current={'seed':self.base_seed+self.episode,'near':idx,'far':(idx+2)%15}
        self.last=self.request(dict(op='reset',**self.current));self.start_step=self.steps;self.total_reward=0.;self.record('reset',self.last)
        return np.asarray(self.last['observation'],np.float32),self.last.copy()
    def step(self,action):
        if not self.action_space.contains(action):raise ValueError('Invalid action')
        old=self.last;s=self.request(dict(op='step',action=int(action)));self.steps+=1
        if s['nearPoints']+s['farPoints']-(old['nearPoints']+old['farPoints']) not in (0,1):raise ValueError('Non-authoritative point transition')
        def delta(a,b):return (s[a]-old[a])-(s[b]-old[b])
        reward=self.cfg['reward_point']*delta('nearPoints','farPoints')+self.cfg['reward_game']*delta('nearGameWins','farGameWins')+self.cfg['reward_set']*delta('nearSets','farSets')
        reward+=self.cfg['reward_rejected']*(s['rejected']-old['rejected'])
        if s['done']:
            if s['winner'] not in ('Near','Far') or max(s['nearSets'],s['farSets'])!=2:raise ValueError('False terminal')
            reward+=self.cfg['reward_match']*(1 if s['winner']=='Near' else -1)
        self.total_reward+=reward
        if s['nearPoints']!=old['nearPoints'] or s['farPoints']!=old['farPoints'] or s['attempts']!=old['attempts'] or s['done']:self.record('transition',dict(s,action=int(action),reward=reward))
        if s['done']:
            self.episodes.append(dict(**self.current,steps=self.steps-self.start_step,reward=self.total_reward,final=s));print('UNITY_MATCH',self.episode,s['winner'],s['nearSets'],s['farSets'],'steps',self.steps,flush=True)
        self.last=s
        return np.asarray(s['observation'],np.float32),float(reward),s['done'],False,s.copy()
    def close(self):
        if getattr(self,'wire',None):self.request({'op':'close'});self.wire.close();self.sock.close();self.raw.close();self.wire=None

class Metrics(BaseCallback):
    def __init__(self):super().__init__();self.updates=[]
    def _on_step(self):return True
    def _on_rollout_start(self):
        if self.model._n_updates:
            self.updates.append(dict(steps=self.model.num_timesteps,updates=self.model._n_updates,metrics={k:float(v) for k,v in self.model.logger.name_to_value.items() if k.startswith('train/') and np.isscalar(v)}))
            print('PPO_UPDATE',self.model.num_timesteps,self.model._n_updates,flush=True)

def export(model,path):
    p=model.policy;layers=[p.mlp_extractor.policy_net[0],p.mlp_extractor.policy_net[2],p.action_net]
    d=dict(schema=1,observationVersion=2,actionVersion=1,rewardVersion=1,inputSize=32,hiddenSize=32,actionCount=6,steps=model.num_timesteps,trainingTool='stable-baselines3 PPO')
    for i,l in enumerate(layers,1):d['w'+str(i)]=l.weight.detach().cpu().numpy().ravel().tolist();d['b'+str(i)]=l.bias.detach().cpu().numpy().tolist()
    Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_text(json.dumps(d,separators=(',',':'))+'\n')
    rng=np.random.default_rng(71023);cases=[]
    with torch.no_grad():
        for _ in range(64):
            raw=(rng.uniform(-1,1,32)*SCALES).astype(np.float32);o=normalize(raw)
            logits=p.action_net(p.mlp_extractor.policy_net(torch.tensor(o))).numpy()
            cases.append(dict(raw=raw.tolist(),observation=o.tolist(),logits=logits.tolist(),action=int(np.argmax(logits))))
    return cases

def train(port,csv_path,out,report_path):
    torch.set_num_threads(1);cfg=config(csv_path);report_path=Path(report_path);report_path.parent.mkdir(parents=True,exist_ok=True)
    raw_path=report_path.with_name('training-raw.jsonl');env=UnityMatch(port,cfg,raw_path)
    model=PPO('MlpPolicy',env,seed=cfg['seed'],device='cpu',verbose=0,policy_kwargs={'net_arch':dict(pi=[32,32],vf=[32,32]),'activation_fn':torch.nn.Tanh},
        **{k:cfg[k] for k in ('n_steps','batch_size','n_epochs','learning_rate','gamma','gae_lambda','clip_range','ent_coef','vf_coef','max_grad_norm')})
    initial=weights_hash(model);cb=Metrics();start=time.monotonic()
    try:
        model.learn(cfg['steps'],callback=cb)
        while len(env.episodes)<2:model.learn(cfg['n_steps'],callback=cb,reset_num_timesteps=False)
        final=weights_hash(model);cases=export(model,out)
        checkpoint=Path(__file__).resolve().parents[1]/'.work/full-match-checkpoint';checkpoint.parent.mkdir(exist_ok=True);model.save(checkpoint)
        report=dict(schema=1,passed=False,environment='actual Unity SinglePlayerCourt, authoritative BallFlight/TennisMatch; stepped 0.1 simulation seconds; no surrogate',
            observationVersion=2,actionVersion=1,rewardVersion=1,steps=model.num_timesteps,rolloutUpdates=model.num_timesteps//cfg['n_steps'],optimizerEpochs=model._n_updates,
            episodes=len(env.episodes),matches=len(env.episodes),games=sum(e['final']['nearGameWins']+e['final']['farGameWins'] for e in env.episodes),sets=sum(e['final']['nearSets']+e['final']['farSets'] for e in env.episodes),
            completedMatches=env.episodes,partialFinalState=env.last,config=cfg,configSha256=sha(csv_path),initialWeightsSha256=initial,finalWeightsSha256=final,modelSha256=sha(out),rawSha256=sha(raw_path),
            libraries={k:importlib.metadata.version(k) for k in ('gymnasium','torch','numpy','stable-baselines3')},updates=cb.updates,
            finalLosses={k:float(v) for k,v in model.logger.name_to_value.items() if k.startswith('train/') and np.isscalar(v)},wallSeconds=time.monotonic()-start,
            limitations=['Shot placement tactics learned; deterministic movement, serve, reaction, stroke timing and skill safety executor remain.','Training outcomes are not held-out or human win rates.','Partial final match is recorded and not counted as completed.'])
        if initial==final or model.num_timesteps<65536 or report['rolloutUpdates']<4 or len(env.episodes)<2:raise RuntimeError('Insufficient actual training')
        if not all(math.isfinite(v) for v in report['finalLosses'].values()):raise RuntimeError('Nonfinite training loss')
        report['passed']=True
        report_path.write_text(json.dumps(report,indent=2)+'\n')
        Path(out).with_name('full-match-parity.json').write_text(json.dumps(dict(schema=1,modelSha256=sha(out),cases=cases),indent=2)+'\n')
    finally:env.close()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=18571);p.add_argument('--config',type=Path,default=Path(__file__).with_name('full-match.csv'));p.add_argument('--out',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();train(a.port,a.config,a.out,a.report)
