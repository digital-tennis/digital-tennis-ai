"""PPO tactical placement training; a one-step domain-randomized MDP, not full-match/self-play training."""
import argparse, csv, hashlib, json, math, os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[1]/'.work/plot-cache'))
import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env

ROOT = Path(__file__).resolve().parents[1]
WIDTH, LENGTH = 4.115, 11.885

class Placement(gym.Env):
    def __init__(self, balance, actions, net_height):
        self.b, self.actions, self.net_height = balance, actions, net_height
        self.observation_space = gym.spaces.Box(-2, 2, (12,), dtype=np.float32)
        self.action_space = gym.spaces.Discrete(len(actions))

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        r, b = self.np_random, self.b
        self.context = np.array([r.uniform(-3.6,3.6), r.uniform(.35,2.4), r.uniform(2,10.5),
            r.uniform(-3,3), r.uniform(-4,4), r.uniform(8,20),
            r.uniform(-3.9,3.9), r.uniform(-11,-2), 0, 0, r.uniform(.8,1.2), b['physics.gravity']], dtype=np.float32)
        self.context[8] = self.context[0] + r.uniform(-.5,.5)
        self.context[9] = self.context[2] + r.uniform(-.5,.5)
        self.obs = self.context / np.array([WIDTH,4,LENGTH,30,30,30,WIDTH,LENGTH,WIDTH,LENGTH,2,30],dtype=np.float32)
        return self.obs.copy(), {}

    def reward(self, action):
        # Same ballistic shot equation and yaw/power clamps as AiPolicy.PlanShot.
        x,y,z,_,_,_,ox,oz,_,_,mult,g = map(float,self.context)
        a, b = self.actions[action], self.b
        tx, tz = a[0]*b['ai.target_width'], -a[1]*b['ai.target_depth']
        dz = max(1, z-tz); dx = x-tx
        yaw = np.clip(math.atan2(dx,dz),-math.radians(b['shot.yaw']),math.radians(b['shot.yaw']))
        pitch = math.radians(b['shot.pitch']); distance = dz/math.cos(yaw)
        denominator = 2*math.cos(pitch)**2*(y-b['physics.radius']+distance*math.tan(pitch))
        ideal = math.sqrt(g*distance*distance/denominator) if denominator>0 else b['shot.base_speed']
        power = np.clip((ideal/mult-b['shot.base_speed'])/b['shot.power_speed'],0,b['ai.hard.max_power'])
        speed = (b['shot.base_speed']+power*b['shot.power_speed'])*mult
        vx=-math.sin(yaw)*math.cos(pitch)*speed; vz=-math.cos(yaw)*math.cos(pitch)*speed; vy=math.sin(pitch)*speed
        t=(vy+math.sqrt(vy*vy+2*g*(y-b['physics.radius'])))/g
        lx,lz=x+vx*t,z+vz*t; net_t=-z/vz; net_y=y+vy*net_t-.5*g*net_t*net_t
        if abs(lx)>WIDTH or not -LENGTH<=lz<=0 or net_y<=self.net_height+b['physics.radius']: return -1.0
        # Placement pressure: opponent's necessary travel relative to the available flight time.
        travel=math.hypot(lx-ox,lz-oz)
        return float(np.clip(travel/(b['move.speed']*t),0,2)-.5)

    def step(self, action):
        return self.obs.copy(), self.reward(int(action)), True, False, {}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--balance',type=Path,default=ROOT/'tests/balance.csv')
    p.add_argument('--actions',type=Path,default=ROOT/'Training/actions.csv')
    p.add_argument('--environment',type=Path,default=ROOT/'Training/environment.csv')
    p.add_argument('--out',type=Path,default=ROOT/'Runtime/Resources/DigitalTennisAI')
    p.add_argument('--steps',type=int,default=65536); p.add_argument('--seed',type=int,default=20261019)
    a=p.parse_args();torch.set_num_threads(1)
    with a.balance.open() as f:b={r['key']:float(r['value']) for r in csv.DictReader(f)}
    with a.actions.open() as f:actions=[(float(r['width_factor']),float(r['depth_factor'])) for r in csv.DictReader(f)]
    with a.environment.open() as f:environment={r['key']:float(r['value']) for r in csv.DictReader(f)}
    if len(actions)!=6 or not all(-1<=w<=1 and .2<=d<=1.4 for w,d in actions):raise SystemExit('Invalid action schema')
    if not 0<environment['net_height']<2:raise SystemExit('Invalid net height')
    env=Placement(b,actions,environment['net_height']);check_env(env)
    model=PPO('MlpPolicy',env,seed=a.seed,n_steps=1024,batch_size=128,n_epochs=6,learning_rate=.0007,
        gamma=0,ent_coef=.01,policy_kwargs={'net_arch':dict(pi=[32,32],vf=[32,32]),'activation_fn':torch.nn.Tanh},device='cpu',verbose=0)
    model.learn(a.steps)
    a.out.mkdir(parents=True,exist_ok=True); (ROOT/'.work').mkdir(exist_ok=True); model.save(str(ROOT/'.work/placement-checkpoint'))
    actor=model.policy;linear=[actor.mlp_extractor.policy_net[0],actor.mlp_extractor.policy_net[2],actor.action_net]
    data=dict(schema=1,inputSize=12,hiddenSize=32,actionCount=6,seed=a.seed,steps=model.num_timesteps,trainingTool='stable-baselines3 PPO',
        widthFactors=[x[0] for x in actions],depthFactors=[x[1] for x in actions])
    for i,l in enumerate(linear,1):
        data['w'+str(i)]=l.weight.detach().cpu().numpy().ravel().tolist();data['b'+str(i)]=l.bias.detach().cpu().numpy().tolist()
    model_path=a.out/'placement-ppo.json';model_path.write_text(json.dumps(data,separators=(',',':'))+'\n')
    scores=[];randoms=[];best=[];counts=[0]*6;cases=[];eval_env=Placement(b,actions,environment['net_height']);rng=np.random.default_rng(a.seed+2)
    for i in range(2048):
        obs,_=eval_env.reset(seed=a.seed+100000+i);action=int(model.predict(obs,deterministic=True)[0]);counts[action]+=1
        scores.append(eval_env.reward(action));randoms.append(eval_env.reward(int(rng.integers(6))));best.append(max(eval_env.reward(j) for j in range(6)))
        if i<64:cases.append(dict(observation=obs.tolist(),action=action))
    report=dict(seed=a.seed,heldOutEpisodes=len(scores),trainedReward=float(np.mean(scores)),randomReward=float(np.mean(randoms)),oracleReward=float(np.mean(best)),
        actions=counts,modelSha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),balanceSha256=hashlib.sha256(a.balance.read_bytes()).hexdigest(),
        environmentSha256=hashlib.sha256(a.environment.read_bytes()).hexdigest(),netHeight=environment['net_height'],
        environment='one-step placement-pressure MDP; ballistic landing/net checks, not full-match win rate',portableCases=cases)
    (ROOT/'Models').mkdir(exist_ok=True); (ROOT/'Models/placement-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='portableCases'},indent=2))
    if report['trainedReward']<=report['randomReward']+.1:raise SystemExit('Policy did not improve over held-out random baseline')

if __name__=='__main__': main()
