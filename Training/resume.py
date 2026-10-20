"""Two-process interruption/resumption over one suspended authoritative Unity lease."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import pickle
import random
import os
import numpy as np
import torch
from stable_baselines3 import PPO
from full_match import config,sha,weights_hash,export
from self_play import Actor,Duel,Snapshots,settings
import checkpoint as cp


def run(root,output,port,phase,lease):
    root=Path(root);output=Path(output);torch.set_num_threads(1)
    cfg=config(root/'Training/full-match.csv');sp=settings(root/'Training/self-play.csv')
    prior=json.loads((output/'self-play.json').read_text())
    if not prior['passed']:raise ValueError('Executed self-play required')
    sources=[root/'Training'/n for n in ('checkpoint.py','resume.py','self_play.py','self-play.csv','full_match.py','full-match.csv','requirements-lock.txt')]
    game=output.parents[2]
    sources += [game/'Assets/Tests/PlayMode/FullMatchResumeTests.cs',game/'Assets/Scripts/Runtime/FullMatchObservation.cs',game/'tools/run-ai-resume.py']
    sources += list((game/'Assets/StreamingAssets/Balance').glob('*.csv'))
    sources += list((game/'Assets/Scripts/Runtime').rglob('*.cs'))
    sources += list((game/'Assets/Scenes').glob('*.unity'))
    sources += [game/'ProjectSettings/ProjectVersion.txt',game/'Packages/manifest.json',game/'tools/unity.sh']
    sources=list(dict.fromkeys(sources))
    contract=dict(observationVersion=2,actionVersion=1,rewardVersion=1,inputSize=32,actionCount=6,normalization='fixed Unity v2 [-2,2]; no running mean/variance',
        config=cfg,selfPlay=sp,hashes={str(p.relative_to(root)) if p.is_relative_to(root) else str(p.relative_to(game)):sha(p) for p in sources},
        environment='Unity 6000.3.26f1 authoritative default rules 3/6/6/7; suspended synchronous bridge lease')
    pool=[Actor(output/'full-match-ppo.json')]+[Actor(output/'self-play-pool'/s['file']) for s in prior['snapshots']]
    raw=output/('resume-interrupt-raw.jsonl' if phase=='interrupt' else 'resume-continuation-raw.jsonl')
    env=Duel(port,cfg,raw,pool,sp['seed']);env.lease=lease
    folder=output/'resume-pool';folder.mkdir(exist_ok=True)
    checkpoint=root/'.work/complete-checkpoints'
    detached=False
    try:
        if phase=='interrupt':
            # Legacy actor-only self-play saved after a frozen finish-only segment.
            # A legal new match starts BEFORE establishing the new complete checkpoint.
            env.episode=len(prior['schedule']);env.schedule=copy.deepcopy(prior['schedule'])
            model=PPO.load(root/'.work/self-play-checkpoint.zip',env=env,device='cpu')
            if weights_hash(model)!=prior['finalWeightsSha256']:raise ValueError('Self-play source model mismatch')
            initial_step=model.num_timesteps;initial_updates=model._n_updates
            cb=Snapshots(env,folder,sp['snapshot_interval']);cb.entries=copy.deepcopy(prior['snapshots'])
            model.learn(4096,callback=cb,reset_num_timesteps=False)
            state=cp.capture(model,env,cb.entries)
            state['run']=dict(initialStep=initial_step,initialUpdates=initial_updates,weights=weights_hash(model),pool=[a.digest for a in env.pool],
                schedule=copy.deepcopy(env.schedule),interruptPid=os.getpid())
            generation=cp.save(checkpoint,model,state,contract,env.pool)
            # Record an expected RNG probe without advancing the saved stream.
            saved_rng=cp.rng_state()
            expected=[random.random(),float(np.random.random()),float(torch.rand(()))]
            cp.restore_rng(saved_rng)
            receipt=dict(generation=generation,expectedRng=expected,pid=os.getpid())
            (root/'.work/resume-interruption.json').write_text(json.dumps(receipt))
            detached=True
            print('CHECKPOINT_SAVED_TRAINER_EXIT',os.getpid(),state['globalStep'],flush=True)
            return
        receipt=json.loads((root/'.work/resume-interruption.json').read_text())
        if receipt['pid']==os.getpid():raise ValueError('Resume must run in a new trainer process')
        # New Python env contains no match/monitor/RNG/schedule state. Load restores it.
        env.rng=[np.random.default_rng(0),np.random.default_rng(1)]
        model,state=cp.load(checkpoint,env,contract,root/'.work/restored-pool')
        before=state['run'];before_weights=before['weights'];before_pool=before['pool'];before_schedule=before['schedule']
        saved_rng=cp.rng_state()
        actual=[random.random(),float(np.random.random()),float(torch.rand(()))]
        assert receipt['expectedRng']==actual
        cp.restore_rng(saved_rng)
        assert weights_hash(model)==before_weights and env.schedule==before_schedule
        assert [a.digest for a in env.pool]==before_pool and cp.optimizer_hash(model)==state['optimizerSha256']
        after_load=dict(globalStep=model.num_timesteps,updates=model._n_updates,optimizerSha256=cp.optimizer_hash(model),weightsSha256=weights_hash(model),pool=before_pool,
            scheduleSha256=cp.fingerprint(env.schedule),environmentSha256=cp.fingerprint(env.last),sideRngSha256=cp.fingerprint([g.bit_generator.state for g in env.rng]))
        cb=Snapshots(env,folder,sp['snapshot_interval']);cb.entries=state['snapshots']
        model.learn(8192,callback=cb,reset_num_timesteps=False)
        final=cp.capture(model,env,cb.entries)
        final_generation=cp.save(checkpoint,model,final,contract,env.pool)
        assert model.num_timesteps-state['globalStep']==8192 and model._n_updates-state['updates']>=2
        assert weights_hash(model)!=before_weights and cp.optimizer_hash(model)!=state['optimizerSha256']
        assert env.schedule[:len(before_schedule)]==before_schedule and [a.digest for a in env.pool][:len(before_pool)]==before_pool
        export(model,output/'resume-ppo.json');env.raw.flush()
        combined=(output/'resume-interrupt-raw.jsonl').read_bytes()+raw.read_bytes()
        compressed=output/'resume-raw.jsonl.gz';compressed.write_bytes(gzip.compress(combined,mtime=0))
        report=dict(schema=1,passed=True,contract=contract,initialSelfPlayStep=before['initialStep'],initialSelfPlayUpdates=before['initialUpdates'],warmupSteps=4096,
            interruptedProcessPid=receipt['pid'],resumedProcessPid=os.getpid(),interruptedTrainerExited=True,
            checkpointGeneration=receipt['generation'],finalGeneration=final_generation,checkpointStep=state['globalStep'],checkpointUpdates=state['updates'],
            loaded=after_load,finalStep=model.num_timesteps,finalUpdates=model._n_updates,additionalSteps=8192,additionalRolloutUpdates=8192//cfg['n_steps'],additionalOptimizerEpochs=model._n_updates-state['updates'],
            optimizerBefore=state['optimizerSha256'],optimizerAfter=cp.optimizer_hash(model),weightsBefore=before_weights,weightsAfter=weights_hash(model),rngRestored=receipt['expectedRng']==actual,
            poolBefore=before_pool,poolAfter=[a.digest for a in env.pool],scheduleBefore=before_schedule,scheduleAfter=env.schedule,snapshots=cb.entries,
            environmentBeforeSha256=cp.fingerprint(state['environment']['last']),environmentAfterLoadSha256=after_load['environmentSha256'],
            sideRngBeforeSha256=cp.fingerprint(state['sideRng']),sideRngAfterLoadSha256=after_load['sideRngSha256'],
            normalization=state['normalization'],rawFile=compressed.name,rawSha256=sha(compressed),modelSha256=sha(output/'resume-ppo.json'),
            completedMatches=env.episodes,partialFinalState=env.last,
            limitations=['Unity world stays suspended on a live synchronous bridge lease across trainer process exit/restart. Lost/restarted Unity or mismatched state is rejected; no silent fresh-world resume.',
                'Checkpoint at fully optimized rollout boundary only; no pending rollout/gradient is discarded.',
                'Prior actor-only self-play checkpoint bootstraps one fresh legal match before warmup; complete checkpoint never resets its partial match.',
                'Deterministic short uninterrupted/resumed parity is tested in a controlled Gym fixture. Unity cross-launch bitwise determinism is not asserted; live lease compares exact state with zero intervening physics steps.',
                'Resume segment may end mid-match; completion is never fabricated. No hardware/Windows/WAN/Mac-window claims in this AC.'])
        (output/'resume.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:report[k] for k in ('passed','checkpointStep','finalStep','additionalSteps','additionalRolloutUpdates','additionalOptimizerEpochs','rngRestored')}),flush=True)
    finally:
        if detached:
            env.raw.close();env.wire.close();env.sock.close();env.wire=None
        else:env.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--phase',choices=['interrupt','continue'],required=True);p.add_argument('--lease',required=True);a=p.parse_args();run(a.root,a.output,a.port,a.phase,a.lease)
