"""Frozen snapshot-pool PPO; every transition comes from the Unity test bridge."""
import argparse
import csv
import json
import math
import time
from pathlib import Path
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from full_match import UnityMatch, config, export, sha, weights_hash


def settings(path):
    rows=list(csv.DictReader(Path(path).open()))
    expected={'steps','snapshot_interval','seed','evaluation_seed'}
    if len(rows)!=4 or {r['key'] for r in rows}!=expected:raise ValueError('Self-play CSV keys')
    d={}
    for r in rows:
        v=float(r['value'])
        if not math.isfinite(v) or not v.is_integer() or not 1<=v<=2147483000:raise ValueError('Self-play CSV range/type')
        d[r['key']]=int(v)
    if d['steps']<32768 or d['snapshot_interval']<2048 or d['snapshot_interval']%2048 or d['steps']%2048:raise ValueError('Self-play budget/alignment')
    return d


class Actor:
    """Read-only numpy copy; no optimizer, normalization updates, shared RNG or recurrence."""
    def __init__(self,path):
        self.path=Path(path);self.digest=sha(path);d=json.loads(self.path.read_text())
        if [d[k] for k in ('observationVersion','actionVersion','inputSize','hiddenSize','actionCount')]!=[2,1,32,32,6]:raise ValueError('Snapshot schema')
        self.layers=[]
        for i,shape in enumerate([(32,32),(32,32),(6,32)],1):
            w=np.asarray(d['w'+str(i)],np.float32).reshape(shape);b=np.asarray(d['b'+str(i)],np.float32)
            if b.shape!=(shape[0],) or not np.isfinite(w).all() or not np.isfinite(b).all():raise ValueError('Snapshot shape/finite')
            w.flags.writeable=b.flags.writeable=False;self.layers.append((w,b))
    def predict(self,o):
        x=np.asarray(o,np.float32)
        if x.shape!=(32,) or not np.isfinite(x).all() or np.max(np.abs(x))>2:raise ValueError('Snapshot observation')
        for i,(w,b) in enumerate(self.layers):
            x=w@x+b
            if i<2:x=np.tanh(x)
        return int(np.argmax(x))
    def verify(self):
        if sha(self.path)!=self.digest:raise ValueError('Frozen snapshot changed')


class Duel(UnityMatch):
    def __init__(self,port,cfg,raw,pool,seed):
        super().__init__(port,cfg,raw);self.base_seed=seed;self.pool=pool;self.schedule=[];self.eval_case=None
    def reset(self,*,seed=None,options=None):
        # Gym owns a separate seed; physical-side action randomness lives in independent streams.
        if self.last is not None and not self.last['done']:raise RuntimeError('Nonterminal reset')
        self.episode+=1
        if self.eval_case is None:
            self.side=(self.episode-1)%2;self.opponent=self.pool[(self.episode-1)%len(self.pool)];kind='frozen'
            near=(self.episode-1)%15;far=(near+2)%15
            matchseed=self.base_seed+self.episode
        else:
            case=self.eval_case;self.side=case['side'];self.opponent=self.pool[0];kind=case['baseline'];near=case['near'];far=case['far'];matchseed=case['seed']
        self.kind=kind;self.rng=[np.random.default_rng(matchseed),np.random.default_rng(matchseed+7919)]
        self.current=dict(seed=matchseed,near=near,far=far,learnerSide='Near' if self.side==0 else 'Far',opponent=kind,opponentSha256=self.opponent.digest if kind=='frozen' else None)
        self.schedule.append(dict(episode=self.episode,step=self.steps,availablePool=[a.digest for a in self.pool],**self.current))
        self.last=self.request(dict(op='reset',seed=matchseed,near=near,far=far));self.start_step=self.steps;self.total_reward=0.;self.record('reset',self.last)
        return self.observe(self.last),self.last.copy()
    def observe(self,s,side=None):return np.asarray(s['observation' if (self.side if side is None else side)==0 else 'farObservation'],np.float32)
    def request(self,data):
        s=super().request(data)
        if data['op']!='close':
            o=np.asarray(s['farObservation'],np.float32)
            if not self.observation_space.contains(o) or s['farAttempts']!=s['farHits']+s['farRejected']:raise ValueError('Far observation/gates')
            if s['isolationChecks']!=2:raise ValueError('Pause/online/reset isolation not exercised')
        return s
    def step(self,action):
        if not self.action_space.contains(action):raise ValueError('Learner action')
        old=self.last;other=1-self.side
        if self.kind=='random':op=int(self.rng[other].integers(6))
        elif self.kind=='scripted':op=-1
        else:op=self.opponent.predict(self.observe(old,other))
        actions=[None,None];actions[self.side]=int(action);actions[other]=op
        s=self.request(dict(op='step',nearAction=actions[0],farAction=actions[1]));self.steps+=1
        if s['nearPoints']+s['farPoints']-old['nearPoints']-old['farPoints'] not in (0,1):raise ValueError('Point transition')
        def delta(a,b):return ((s[a]-old[a])-(s[b]-old[b]))*(1 if self.side==0 else -1)
        reward=self.cfg['reward_point']*delta('nearPoints','farPoints')+self.cfg['reward_game']*delta('nearGameWins','farGameWins')+self.cfg['reward_set']*delta('nearSets','farSets')
        key='rejected' if self.side==0 else 'farRejected';reward+=self.cfg['reward_rejected']*(s[key]-old[key])
        if s['done']:
            if max(s['nearSets'],s['farSets'])!=2 or s['winner'] not in ('Near','Far'):raise ValueError('False done')
            reward+=self.cfg['reward_match']*(1 if s['winner']==self.current['learnerSide'] else -1)
        self.total_reward+=reward
        changed=any(s[k]!=old[k] for k in ('nearPoints','farPoints','attempts','farAttempts')) or s['done']
        if changed:self.record('transition',dict(s,nearAction=actions[0],farAction=actions[1],reward=reward))
        if s['done']:
            self.opponent.verify();self.episodes.append(dict(**self.current,steps=self.steps-self.start_step,reward=self.total_reward,final=s));print('UNITY_SELF_PLAY_MATCH',len(self.episodes),self.current,s['winner'],'steps',self.steps,flush=True)
        self.last=s
        return self.observe(s),float(reward),s['done'],False,s.copy()


class Snapshots(BaseCallback):
    def __init__(self,env,folder,interval):super().__init__();self.duel=env;self.folder=folder;self.interval=interval;self.entries=[]
    def _on_step(self):return True
    def _on_rollout_start(self):
        step=self.model.num_timesteps
        if step and step%self.interval==0:
            path=self.folder/f'snapshot-{step}.json'
            if path.exists():raise RuntimeError('Snapshot overwrite')
            export(self.model,path);actor=Actor(path);self.duel.pool.append(actor);self.entries.append(dict(step=step,sha256=actor.digest,file=path.name))
            print('FROZEN_POOL_SNAPSHOT',step,actor.digest,flush=True)


def run(port,root,output):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(1);cfg=config(Path(__file__).with_name('full-match.csv'));sp=settings(Path(__file__).with_name('self-play.csv'))
    training=json.loads((output/'training.json').read_text())
    if not training['passed'] or training['steps']<65536:raise RuntimeError('Baseline training must precede self-play')
    initial_path=output/'full-match-ppo.json';initial_actor=Actor(initial_path)
    folder=output/'self-play-pool';folder.mkdir(exist_ok=True)
    env=Duel(port,cfg,output/'self-play-raw.jsonl',[initial_actor],sp['seed'])
    model=PPO.load(root/'.work/full-match-checkpoint.zip',env=env,device='cpu')
    if weights_hash(model)!=training['finalWeightsSha256']:raise RuntimeError('Initial trained checkpoint mismatch')
    initial=weights_hash(model);old_updates=model._n_updates
    cb=Snapshots(env,folder,sp['snapshot_interval']);start=time.monotonic()
    try:
        model.learn(sp['steps'],callback=cb)
        while len(env.episodes)<2 or len({e['learnerSide'] for e in env.episodes})<2 or len({e['opponentSha256'] for e in env.episodes})<2:
            model.learn(cfg['n_steps'],callback=cb,reset_num_timesteps=False)
        # Complete the last real match for a legal reset into evaluation, using a frozen actor.
        target_steps=model.num_timesteps
        final_path=output/'self-play-ppo.json';export(model,final_path);final_actor=Actor(final_path)
        while not env.last['done']:env.step(final_actor.predict(env.observe(env.last)))
        model.save(root/'.work/self-play-checkpoint.zip')
        losses={k:float(v) for k,v in model.logger.name_to_value.items() if k.startswith('train/') and np.isscalar(v)}
        assert losses and all(math.isfinite(v) for v in losses.values()) and initial!=weights_hash(model)
        report=dict(schema=1,passed=True,environment='actual authoritative Unity SinglePlayerCourt; test-only two-player ordinary input fixture',steps=target_steps,trajectorySteps=env.steps,rolloutUpdates=target_steps//cfg['n_steps'],optimizerEpochs=model._n_updates-old_updates,
            matches=len(env.episodes),completedMatches=env.episodes,schedule=env.schedule,snapshots=cb.entries,initialWeightsSha256=initial,finalWeightsSha256=weights_hash(model),modelSha256=sha(final_path),
            baselineTrainingSha256=sha(output/'training.json'),initialModelSha256=initial_actor.digest,rawSha256=sha(output/'self-play-raw.jsonl'),config=sp,configSha256=sha(Path(__file__).with_name('self-play.csv')),
            ppoConfig=cfg,finalLosses=losses,wallSeconds=time.monotonic()-start,finishOnlySteps=env.steps-target_steps,
            stateIsolation='Separate Near/Far AiPolicy random/reaction/tick/session/event state reset per actual completed match. Frozen actor has no recurrent or normalization state; per-side numpy random streams. Opponent fixed for entire match.',
            limitations=['Placement tactics only; deterministic movement, serve, timing, skill safety remain.','Symmetric Hard executors with ordinary AutomaticCourtMovement in opt-in Practice fixture; no demo swings/auto serve.','Finish-only steps are frozen and excluded from PPO budget.','No guaranteed improvement or human win-rate claim.'])
        for a in env.pool:a.verify()
        (output/'self-play.json').write_text(json.dumps(report,indent=2)+'\n')
        # Evaluation has no optimizer calls. Held-out cohort differs from training offset+2 and seeds.
        evaluation_before=weights_hash(model);env.raw.close();env.raw=(output/'held-out-raw.jsonl').open('w');env.steps=0;env.episode=0;env.episodes=[];env.schedule=[];env.pool=[initial_actor]
        for index,kind in enumerate(('scripted','random','frozen')):
            for side in (0,1):
                env.eval_case=dict(baseline=kind,side=side,near=index*3,far=index*3+7,seed=sp['evaluation_seed']+index*101+side)
                obs,_=env.reset()
                while True:
                    obs,_,done,_,_=env.step(final_actor.predict(obs))
                    if done:break
        assert evaluation_before==weights_hash(model);final_actor.verify();initial_actor.verify()
        held=dict(schema=1,passed=True,frozen=True,evaluationTrainingUpdates=0,modelSha256=final_actor.digest,baselineModelSha256=initial_actor.digest,weightsBefore=evaluation_before,weightsAfter=weights_hash(model),
            matches=len(env.episodes),completedMatches=env.episodes,schedule=env.schedule,rawSha256=sha(output/'held-out-raw.jsonl'),
            comparisons=[dict(baseline=k,matches=2,wins=sum(e['final']['winner']==e['learnerSide'] for e in env.episodes if e['opponent']==k)) for k in ('scripted','random','frozen')],
            limitations=['Six seeded actual default-rules matches, not population estimates or guaranteed improvement.','Frozen baseline is pre-self-play full-match PPO; scripted uses away-from-opponent deep placement; random samples six placements independently.','Same Hard timing/serve/skill executor and ordinary movement on both sides; learning covers shot tactics.','No hardware, Windows, WAN or ordinary Mac-window verification in this AC.'])
        (output/'held-out.json').write_text(json.dumps(held,indent=2)+'\n')
    finally:env.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=18572);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.port,a.root,a.output)
