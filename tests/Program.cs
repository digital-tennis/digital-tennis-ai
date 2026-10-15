using System;
using System.Collections.Generic;
using System.Linq;
using DigitalTennis.AI;

static class Program
{
    static int passed;
    static void Require(bool ok, string message) { if (!ok) throw new Exception(message); }
    static void Near(float actual, float expected, float tolerance = 0.001f) => Require(Math.Abs(actual - expected) <= tolerance, $"{actual} != {expected}");
    static void Check(string name, Action check) { check(); passed++; Console.WriteLine($"PASS {name}"); }
    static AiState State(long tick = 1, ulong ballId = 1, float dt = 0.05f, AiPhase phase = AiPhase.Rally,
        int player = 1, Vec3? ball = null, Vec3? position = null, Vec3? velocity = null, bool online = false,
        bool stopped = false, int bounces = 1, Vec3? opponent = null) => new AiState(tick, dt, player,
            position ?? new Vec3(0, .85f, player == 1 ? 6 : -6), opponent ?? new Vec3(1, .85f, player == 1 ? -8 : 8),
            ball ?? new Vec3(0, 1, player == 1 ? 6 : -6), velocity ?? new Vec3(0, 2, player == 1 ? 12 : -12),
            phase, bounces, ballId, 1-player, true, stopped, online);
    static uint TryingSeed(Difficulty difficulty)
    {
        for (uint seed=1;seed<100;seed++)
        {
            var p=new AiPolicy(difficulty,seed); p.Decide(State(dt:1));
            if(p.IntentionalMisses==0)return seed;
        }
        throw new Exception("No trying seed");
    }
    static AiDecision ReachReaction(AiPolicy policy, int player = 1, Vec3? ball = null, Vec3? position = null, Vec3? opponent = null)
    {
        AiDecision decision=default;
        for(int i=1;i<=40;i++)
        {
            decision=policy.Decide(State(i,dt:.01f,player:player,ball:ball,position:position,opponent:opponent));
            if(decision.ShouldSwing)return decision;
        }
        return decision;
    }
    static void Main()
    {
        Check("character skill timing stays deterministic and inactive outside a valid returned rally",()=>{
            Require(!AiSkillPolicy.ShouldActivate(State(),Difficulty.Easy,2,0,true),"easy saves three stocks");
            Require(AiSkillPolicy.ShouldActivate(State(),Difficulty.Easy,3,0,true),"easy uses at cap");
            Require(AiSkillPolicy.ShouldActivate(State(),Difficulty.Medium,2,0,true),"medium two stocks");
            Require(AiSkillPolicy.ShouldActivate(State(),Difficulty.Hard,1,0,true),"hard one stock");
            foreach(var stock in new[]{0,4}) Require(!AiSkillPolicy.ShouldActivate(State(),Difficulty.Hard,stock,0,true),"stock bounds");
            Require(!AiSkillPolicy.ShouldActivate(State(online:true),Difficulty.Hard,3,0,true),"online off");
            Require(!AiSkillPolicy.ShouldActivate(State(phase:AiPhase.Paused),Difficulty.Hard,3,0,true),"pause off");
            Require(!AiSkillPolicy.ShouldActivate(State(),Difficulty.Hard,3,1,true),"no active buff stacking");
            Require(!AiSkillPolicy.ShouldActivate(State(),Difficulty.Hard,3,0,false),"no miss charging activation");
        });
        Check("independent numerical landing example",()=>{
            var p=BallPrediction.Landing(new Vec3(0,1,0),new Vec3(2,0,4));
            Require(p.Valid,"valid root");Near(p.TimeToBounce,.451524f,.0001f);Near(p.Position.X,.903047f);Near(p.Position.Z,1.806095f);
        });
        Check("invalid predictions return finite invalid results",()=>{
            foreach(var p in new[]{BallPrediction.Landing(new Vec3(0,-1,0),new Vec3(0,1,0)),
                BallPrediction.Landing(new Vec3(0,1,0),new Vec3(0,0,1),0),
                BallPrediction.Landing(new Vec3(float.NaN,1,0),new Vec3(0,0,1)),
                BallPrediction.Landing(new Vec3(0,100,0),new Vec3(0,0,1)),
                BallPrediction.Landing(new Vec3(0,1,0),new Vec3(0,0,1),stopped:true)}) Require(!p.Valid&&p.Position.IsFinite,"invalid prediction");
        });
        Check("court clamp uses own half and inclusive lines",()=>{
            var near=BallPrediction.Clamp(new Vec3(100,0,-100),0,.85f);Near(near.X,4.115f);Near(near.Z,-11.885f);
            Near(BallPrediction.Clamp(new Vec3(0,0,-100),1,.85f).Z,.8f);
        });
        Check("post-bounce target agrees with reference serve",()=>{
            var state=new AiState(1,.02f,1,new Vec3(-1.5f,.85f,9),new Vec3(1.5f,.85f,-12.6f),
                new Vec3(1.5f,2.2f,-12.6f),new Vec3(-2.5f,4.152667f,13.833334f),AiPhase.ServeInFlight,0,1,0);
            var target=BallPrediction.ContactTarget(state);Require(target.Z>5&&target.Z<8,"post-bounce contact");
            Require(target.X < -1&&target.X > -3,"reference x");
        });
        Check("settings exactly preserve difficulty reaction/error/probability",()=>{
            var easy=DifficultySettings.For(Difficulty.Easy);var medium=DifficultySettings.For(Difficulty.Medium);var hard=DifficultySettings.For(Difficulty.Hard);
            Near(easy.ReactionSeconds,.35f);Near(medium.ReactionSeconds,.2f);Near(hard.ReactionSeconds,.1f);
            Near(easy.PositionError,1.5f);Near(medium.PositionError,.8f);Near(hard.PositionError,.25f);
            Near(easy.SwingProbability,.65f);Near(medium.SwingProbability,.85f);Near(hard.SwingProbability,.95f);
            try{new AiPolicy((Difficulty)99,1);throw new Exception("Expected invalid difficulty");}catch(ArgumentOutOfRangeException){}
        });
        foreach(var difficulty in Enum.GetValues<Difficulty>())
        {
            Check($"{difficulty}: reaction boundary and one swing",()=>{
                var policy=new AiPolicy(difficulty,TryingSeed(difficulty));
                for(int i=1;i<=50;i++)
                {
                    var d=policy.Decide(State(i,dt:.01f));
                    if(policy.ReactionElapsed+1e-6<policy.Settings.ReactionSeconds) Require(!d.ShouldSwing,"early reaction");
                }
                Require(policy.Swings==1&&policy.Samples==1,"one swing/sample");
            });
            Check($"{difficulty}: seed replay and bounded error",()=>{
                var a=new AiPolicy(difficulty,42);var b=new AiPolicy(difficulty,42);
                for(int i=1;i<=1000;i++)
                {
                    var state=State(i,(ulong)((i-1)/10+1),.05f);
                    var before=state.BallPosition.ToString();var da=a.Decide(state);var db=b.Decide(state);
                    Require(da.ToString()==db.ToString(),"replay mismatch");Require(state.BallPosition.ToString()==before,"input mutation");
                    Require(Math.Abs(a.PositionError.X)<=a.Settings.PositionError&&Math.Abs(a.PositionError.Z)<=a.Settings.PositionError,"error bounds");
                    Require(da.MoveTarget.IsFinite&&da.MoveTarget.Z>=.8f&&da.MoveTarget.Z<=11.885f,"target bounds");
                }
                Require(a.Samples==100&&a.Swings<=100,"sample count");
            });
            Check($"{difficulty}: ten thousand sampled attempts match probability",()=>{
                var p=new AiPolicy(difficulty,42);
                for(int i=1;i<=10000;i++)p.Decide(State(i,(ulong)i,1));
                float rate=1-p.IntentionalMisses/10000f;
                Require(Math.Abs(rate-p.Settings.SwingProbability)<.025f,"probability drift");
                Console.WriteLine($"OBSERVED {difficulty} attempt_rate={rate:F4}, expected={p.Settings.SwingProbability:F2}");
                Require(p.Samples==10000,"one sample set per incoming ball");
            });
        }
        Check("150ms distinguishes hard from medium/easy",()=>{
            foreach(var d in Enum.GetValues<Difficulty>())
            {
                var policy=new AiPolicy(d,TryingSeed(d)); AiDecision decision=default;
                for(int i=1;i<=3;i++) decision=policy.Decide(State(i));
                Require(policy.Swings==(d==Difficulty.Hard?1:0),"150ms boundary");
            }
        });
        Check("pause/online/end phases neither sample nor advance reaction",()=>{
            var p=new AiPolicy(Difficulty.Hard,TryingSeed(Difficulty.Hard));p.Decide(State(dt:.04f));
            foreach(var phase in new[]{AiPhase.Paused,AiPhase.WaitServe,AiPhase.PointEnd,AiPhase.MatchEnd})
                Require(!p.Decide(State(2,2,1,phase)).ShouldSwing,"inactive swing");
            Require(!p.Decide(State(3,2,1,online:true)).ShouldSwing,"online swing");Near(p.ReactionElapsed,.04f);Require(p.Samples==1,"inactive samples");
            Require(!p.Decide(State(4,dt:.04f)).ShouldSwing,"paused timer advanced");
            Require(p.Decide(State(5,dt:.02f)).ShouldSwing,"resume should react");
        });
        Check("duplicate tick cannot advance reaction or emit twice",()=>{
            var p=new AiPolicy(Difficulty.Hard,TryingSeed(Difficulty.Hard));
            for(int i=0;i<10;i++)Require(!p.Decide(State(dt:.05f)).ShouldSwing,"duplicate tick reaction");
            Require(p.Decide(State(2,dt:.05f)).ShouldSwing,"second distinct tick");
            Require(!p.Decide(State(2,dt:.05f)).ShouldSwing,"duplicate swing");
        });
        Check("invalid inputs and unavailable ball never swing",()=>{
            foreach(var state in new[]{State(dt:0),State(dt:float.NaN),State(dt:2),State(player:9),
                State(ball:new Vec3(float.PositiveInfinity,1,6)),State(stopped:true),State(ballId:0),State(bounces:2)})
                Require(!new AiPolicy(Difficulty.Hard,42).Decide(state).ShouldSwing,"invalid swing");
        });
        Check("wrong court, high/low and distant ball do not swing",()=>{
            foreach(var ball in new[]{new Vec3(0,1,-1),new Vec3(0,.199f,6),new Vec3(0,2.501f,6),new Vec3(3,1,6)})
                Require(!ReachReaction(new AiPolicy(Difficulty.Hard,TryingSeed(Difficulty.Hard)),ball:ball).ShouldSwing,"illegal reach");
        });
        Check("outgoing ball returns home without random sampling",()=>{
            var p=new AiPolicy(Difficulty.Hard,42);var d=p.Decide(State(velocity:new Vec3(0,1,-10)));
            Require(!d.ShouldSwing&&d.Status==AiStatus.Recovering&&p.Samples==0,"outgoing decision");Near(d.MoveTarget.Z,8);
        });
        Check("same ball retains a single sampled target error",()=>{
            var p=new AiPolicy(Difficulty.Hard,42);p.Decide(State());var error=p.PositionError.ToString();
            for(int i=2;i<40;i++)p.Decide(State(i,position:new Vec3(3,.85f,9)));
            Require(p.Samples==1&&p.PositionError.ToString()==error,"resampling");p.Decide(State(40,2));Require(p.Samples==2,"new ball samples");
        });
        Check("both court directions plan legal in-court landing",()=>{
            foreach(int player in new[]{0,1})
            {
                var d=ReachReaction(new AiPolicy(Difficulty.Hard,TryingSeed(Difficulty.Hard)),player);
                Require(d.ShouldSwing&&d.Power01>=0&&d.Power01<=.8f&&Math.Abs(d.AimX)<=1,"valid shot");
                double yaw=d.AimX*25*Math.PI/180,pitch=20*Math.PI/180,speed=10+12*d.Power01;
                float facing=player==0?1:-1;
                var velocity=new Vec3((float)(facing*Math.Sin(yaw)*Math.Cos(pitch)*speed),(float)(Math.Sin(pitch)*speed),(float)(facing*Math.Cos(yaw)*Math.Cos(pitch)*speed));
                var landing=BallPrediction.Landing(new Vec3(0,1,player==0?-6:6),velocity,plane:.12f);
                Require(landing.Valid,"planned landing");Near(landing.Position.Z,player==0?8:-8,.01f);Near(landing.Position.X,-2.5f,.01f);
            }
        });
        Check("stroke follows player's local racket side",()=>{
            var fore=ReachReaction(new AiPolicy(Difficulty.Hard,TryingSeed(Difficulty.Hard)),ball:new Vec3(-.2f,1,6));
            var back=ReachReaction(new AiPolicy(Difficulty.Hard,TryingSeed(Difficulty.Hard)),ball:new Vec3(.2f,1,6));
            Require(fore.Stroke==AiStroke.Forehand&&back.Stroke==AiStroke.Backhand,"stroke selection");
        });
        Console.WriteLine($"ALL {passed} CHECKS PASSED");
    }
}
