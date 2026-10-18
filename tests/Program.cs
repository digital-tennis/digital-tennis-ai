using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Globalization;
using DigitalTennis.AI;
using System.Text.Json;

static class Program
{
    static int passed;
    static readonly Dictionary<string,float> Values = File.ReadAllLines(Path.Combine(AppContext.BaseDirectory,"balance.csv")).Skip(1)
        .Where(x=>x.Length>0).Select(x=>x.Split(',')).ToDictionary(x=>x[0],x=>float.Parse(x[1],CultureInfo.InvariantCulture));
    static readonly AiTuning Tuning = new AiTuning(Values);
    static DifficultySettings Settings(Difficulty d) {
        if(!Enum.IsDefined(typeof(Difficulty),d))throw new ArgumentOutOfRangeException(nameof(d));
        string p="ai."+d.ToString().ToLowerInvariant()+".";
        return new DifficultySettings(d,Values[p+"reaction"],Values[p+"error"],Values[p+"probability"],Values[p+"max_power"],(int)Values[p+"skill_stock"]);
    }
    static AiPolicy Policy(Difficulty d,uint seed) => new AiPolicy(Settings(d),Tuning,seed);
    static void Require(bool ok, string message) { if (!ok) throw new Exception(message); }
    static void Near(float actual, float expected, float tolerance = 0.001f) => Require(Math.Abs(actual - expected) <= tolerance, $"{actual} != {expected}");
    static void Check(string name, Action check) { check(); passed++; Console.WriteLine($"PASS {name}"); }
    static AiState State(long tick = 1, ulong ballId = 1, float dt = 0.05f, AiPhase phase = AiPhase.Rally,
        int player = 1, Vec3? ball = null, Vec3? position = null, Vec3? velocity = null, bool online = false,
        bool stopped = false, int bounces = 1, Vec3? opponent = null) => new AiState(tick, dt, player,
            position ?? new Vec3(0, .85f, player == 1 ? 6 : -6), opponent ?? new Vec3(1, .85f, player == 1 ? -8 : 8),
            ball ?? new Vec3(0, 1, player == 1 ? 6 : -6), velocity ?? new Vec3(0, 2, player == 1 ? 12 : -12),
            phase, bounces, ballId, 1-player, true, stopped, online,Values["physics.gravity"],Values["physics.radius"],Values["physics.bounce"],Values["physics.ground_retention"]);
    static uint TryingSeed(Difficulty difficulty)
    {
        for (uint seed=1;seed<100;seed++)
        {
            var p=Policy(difficulty,seed); p.Decide(State(dt:1));
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
            Require(!AiSkillPolicy.ShouldActivate(State(),Settings(Difficulty.Easy),2,0,true),"easy saves three stocks");
            Require(AiSkillPolicy.ShouldActivate(State(),Settings(Difficulty.Easy),3,0,true),"easy uses at cap");
            Require(AiSkillPolicy.ShouldActivate(State(),Settings(Difficulty.Medium),2,0,true),"medium two stocks");
            Require(AiSkillPolicy.ShouldActivate(State(),Settings(Difficulty.Hard),1,0,true),"hard one stock");
            foreach(var stock in new[]{0,4}) Require(!AiSkillPolicy.ShouldActivate(State(),Settings(Difficulty.Hard),stock,0,true),"stock bounds");
            Require(!AiSkillPolicy.ShouldActivate(State(online:true),Settings(Difficulty.Hard),3,0,true),"online off");
            Require(!AiSkillPolicy.ShouldActivate(State(phase:AiPhase.Paused),Settings(Difficulty.Hard),3,0,true),"pause off");
            Require(!AiSkillPolicy.ShouldActivate(State(),Settings(Difficulty.Hard),3,1,true),"no active buff stacking");
            Require(!AiSkillPolicy.ShouldActivate(State(),Settings(Difficulty.Hard),3,0,false),"no miss charging activation");
        });
        Check("independent numerical landing example",()=>{
            var p=BallPrediction.Landing(new Vec3(0,1,0),new Vec3(2,0,4),9.81f);
            Require(p.Valid,"valid root");Near(p.TimeToBounce,.451524f,.0001f);Near(p.Position.X,.903047f);Near(p.Position.Z,1.806095f);
        });
        Check("invalid predictions return finite invalid results",()=>{
            foreach(var p in new[]{BallPrediction.Landing(new Vec3(0,-1,0),new Vec3(0,1,0),9.81f),
                BallPrediction.Landing(new Vec3(0,1,0),new Vec3(0,0,1),0),
                BallPrediction.Landing(new Vec3(float.NaN,1,0),new Vec3(0,0,1),9.81f),
                BallPrediction.Landing(new Vec3(0,100,0),new Vec3(0,0,1),9.81f),
                BallPrediction.Landing(new Vec3(0,1,0),new Vec3(0,0,1),9.81f,stopped:true)}) Require(!p.Valid&&p.Position.IsFinite,"invalid prediction");
        });
        Check("court clamp uses own half and inclusive lines",()=>{
            var near=BallPrediction.Clamp(new Vec3(100,0,-100),0,.85f,Tuning);Near(near.X,4.115f);Near(near.Z,-11.885f);
            Near(BallPrediction.Clamp(new Vec3(0,0,-100),1,.85f,Tuning).Z,.8f);
        });
        Check("post-bounce target agrees with reference serve",()=>{
            var state=new AiState(1,.02f,1,new Vec3(-1.5f,.85f,9),new Vec3(1.5f,.85f,-12.6f),
                new Vec3(1.5f,2.2f,-12.6f),new Vec3(-2.5f,4.152667f,13.833334f),AiPhase.ServeInFlight,0,1,0, gravity:Values["physics.gravity"],radius:Values["physics.radius"],bounceRestitution:Values["physics.bounce"],speedRetention:Values["physics.ground_retention"]);
            var target=BallPrediction.ContactTarget(state,Tuning);Require(target.Z>5&&target.Z<8,"post-bounce contact");
            Require(target.X < -1&&target.X > -3,"reference x");
        });
        Check("settings exactly preserve difficulty reaction/error/probability",()=>{
            var easy=Settings(Difficulty.Easy);var medium=Settings(Difficulty.Medium);var hard=Settings(Difficulty.Hard);
            Near(easy.ReactionSeconds,.35f);Near(medium.ReactionSeconds,.2f);Near(hard.ReactionSeconds,.1f);
            Near(easy.PositionError,1.5f);Near(medium.PositionError,.8f);Near(hard.PositionError,.25f);
            Near(easy.SwingProbability,.65f);Near(medium.SwingProbability,.85f);Near(hard.SwingProbability,.95f);
            try{Policy((Difficulty)99,1);throw new Exception("Expected invalid difficulty");}catch(ArgumentOutOfRangeException){}
        });
        foreach(var difficulty in Enum.GetValues<Difficulty>())
        {
            Check($"{difficulty}: reaction boundary and one swing",()=>{
                var policy=Policy(difficulty,TryingSeed(difficulty));
                for(int i=1;i<=50;i++)
                {
                    var d=policy.Decide(State(i,dt:.01f));
                    if(policy.ReactionElapsed+1e-6<policy.Settings.ReactionSeconds) Require(!d.ShouldSwing,"early reaction");
                }
                Require(policy.Swings==1&&policy.Samples==1,"one swing/sample");
            });
            Check($"{difficulty}: seed replay and bounded error",()=>{
                var a=Policy(difficulty,42);var b=Policy(difficulty,42);
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
                var p=Policy(difficulty,42);
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
                var policy=Policy(d,TryingSeed(d)); AiDecision decision=default;
                for(int i=1;i<=3;i++) decision=policy.Decide(State(i));
                Require(policy.Swings==(d==Difficulty.Hard?1:0),"150ms boundary");
            }
        });
        Check("pause/online/end phases neither sample nor advance reaction",()=>{
            var p=Policy(Difficulty.Hard,TryingSeed(Difficulty.Hard));p.Decide(State(dt:.04f));
            foreach(var phase in new[]{AiPhase.Paused,AiPhase.WaitServe,AiPhase.PointEnd,AiPhase.MatchEnd})
                Require(!p.Decide(State(2,2,1,phase)).ShouldSwing,"inactive swing");
            Require(!p.Decide(State(3,2,1,online:true)).ShouldSwing,"online swing");Near(p.ReactionElapsed,.04f);Require(p.Samples==1,"inactive samples");
            Require(!p.Decide(State(4,dt:.04f)).ShouldSwing,"paused timer advanced");
            Require(p.Decide(State(5,dt:.02f)).ShouldSwing,"resume should react");
        });
        Check("duplicate tick cannot advance reaction or emit twice",()=>{
            var p=Policy(Difficulty.Hard,TryingSeed(Difficulty.Hard));
            for(int i=0;i<10;i++)Require(!p.Decide(State(dt:.05f)).ShouldSwing,"duplicate tick reaction");
            Require(p.Decide(State(2,dt:.05f)).ShouldSwing,"second distinct tick");
            Require(!p.Decide(State(2,dt:.05f)).ShouldSwing,"duplicate swing");
        });
        Check("invalid inputs and unavailable ball never swing",()=>{
            foreach(var state in new[]{State(dt:0),State(dt:float.NaN),State(dt:2),State(player:9),
                State(ball:new Vec3(float.PositiveInfinity,1,6)),State(stopped:true),State(ballId:0),State(bounces:2)})
                Require(!Policy(Difficulty.Hard,42).Decide(state).ShouldSwing,"invalid swing");
        });
        Check("wrong court, high/low and distant ball do not swing",()=>{
            foreach(var ball in new[]{new Vec3(0,1,-1),new Vec3(0,.199f,6),new Vec3(0,2.501f,6),new Vec3(3,1,6)})
                Require(!ReachReaction(Policy(Difficulty.Hard,TryingSeed(Difficulty.Hard)),ball:ball).ShouldSwing,"illegal reach");
        });
        Check("outgoing ball returns home without random sampling",()=>{
            var p=Policy(Difficulty.Hard,42);var d=p.Decide(State(velocity:new Vec3(0,1,-10)));
            Require(!d.ShouldSwing&&d.Status==AiStatus.Recovering&&p.Samples==0,"outgoing decision");Near(d.MoveTarget.Z,8);
        });
        Check("same ball retains a single sampled target error",()=>{
            var p=Policy(Difficulty.Hard,42);p.Decide(State());var error=p.PositionError.ToString();
            for(int i=2;i<40;i++)p.Decide(State(i,position:new Vec3(3,.85f,9)));
            Require(p.Samples==1&&p.PositionError.ToString()==error,"resampling");p.Decide(State(40,2));Require(p.Samples==2,"new ball samples");
        });
        Check("both court directions plan legal in-court landing",()=>{
            foreach(int player in new[]{0,1})
            {
                var d=ReachReaction(Policy(Difficulty.Hard,TryingSeed(Difficulty.Hard)),player);
                Require(d.ShouldSwing&&d.Power01>=0&&d.Power01<=.8f&&Math.Abs(d.AimX)<=1,"valid shot");
                double yaw=d.AimX*25*Math.PI/180,pitch=20*Math.PI/180,speed=10+12*d.Power01;
                float facing=player==0?1:-1;
                var velocity=new Vec3((float)(facing*Math.Sin(yaw)*Math.Cos(pitch)*speed),(float)(Math.Sin(pitch)*speed),(float)(facing*Math.Cos(yaw)*Math.Cos(pitch)*speed));
                var landing=BallPrediction.Landing(new Vec3(0,1,player==0?-6:6),velocity,9.81f,plane:.12f);
                Require(landing.Valid,"planned landing");Near(landing.Position.Z,player==0?8:-8,.01f);Near(landing.Position.X,-2.5f,.01f);
            }
        });
        Check("stroke follows player's local racket side",()=>{
            var fore=ReachReaction(Policy(Difficulty.Hard,TryingSeed(Difficulty.Hard)),ball:new Vec3(-.2f,1,6));
            var back=ReachReaction(Policy(Difficulty.Hard,TryingSeed(Difficulty.Hard)),ball:new Vec3(.2f,1,6));
            Require(fore.Stroke==AiStroke.Forehand&&back.Stroke==AiStroke.Backhand,"stroke selection");
        });
        Check("injected reaction and shot model change behavior without policy defaults",()=>{
            var custom=new Dictionary<string,float>(Values);custom["shot.base_speed"]=7;custom["shot.power_speed"]=18;custom["shot.yaw"]=32;custom["shot.pitch"]=26;
            var settings=new DifficultySettings(Difficulty.Hard,.3f,0,1,1,2);
            var policy=new AiPolicy(settings,new AiTuning(custom),1);
            for(int i=1;i<=2;i++)Require(!policy.Decide(State(i,dt:.1f)).ShouldSwing,"CSV reaction ignored");
            var shot=policy.Decide(State(3,dt:.1f));Require(shot.ShouldSwing,"custom reaction");
            double yaw=shot.AimX*custom["shot.yaw"]*Math.PI/180,pitch=custom["shot.pitch"]*Math.PI/180,speed=custom["shot.base_speed"]+custom["shot.power_speed"]*shot.Power01;
            var landing=BallPrediction.Landing(new Vec3(0,1,6),new Vec3((float)(-Math.Sin(yaw)*Math.Cos(pitch)*speed),(float)(Math.Sin(pitch)*speed),(float)(-Math.Cos(yaw)*Math.Cos(pitch)*speed)),Values["physics.gravity"],Values["physics.radius"]);
            Require(landing.Valid,"custom landing");Near(landing.Position.Z,-8,.01f);Near(landing.Position.X,-2.5f,.01f);
            Require(!AiSkillPolicy.ShouldActivate(State(),settings,1,0,true),"injected skill threshold");
        });
        PpoModelData Model() => JsonSerializer.Deserialize<PpoModelData>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"placement-ppo.json")),new JsonSerializerOptions{IncludeFields=true});
        Check("PPO portable actor agrees with SB3 on 64 unseen states", () => {
            var actor=new LearnedShotSelector(Model());
            using var report=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"placement-validation.json")));
            foreach(var row in report.RootElement.GetProperty("portableCases").EnumerateArray())
                Require(actor.Predict(row.GetProperty("observation").EnumerateArray().Select(x=>x.GetSingle()).ToArray())==row.GetProperty("action").GetInt32(),"PPO parity");
            Require(report.RootElement.GetProperty("trainedReward").GetDouble()>report.RootElement.GetProperty("randomReward").GetDouble()+.1,"held-out improvement");
        });
        Check("PPO weights are immutable and reject corrupt shapes/non-finite values", () => {
            var data=Model();var actor=new LearnedShotSelector(data);var obs=LearnedShotSelector.Observe(State());int expected=actor.Predict(obs);
            Array.Fill(data.w1,0);Require(actor.Predict(obs)==expected,"actor shared mutable export data");
            data=Model();data.w1[0]=float.NaN;bool rejected=false;try{new LearnedShotSelector(data);}catch(ArgumentException){rejected=true;}Require(rejected,"NaN weights accepted");
            data=Model();data.inputSize++;rejected=false;try{new LearnedShotSelector(data);}catch(ArgumentException){rejected=true;}Require(rejected,"schema accepted");
        });
        Check("PPO observes mirrored court consistently and does not run while inactive", () => {
            var a=LearnedShotSelector.Observe(State());
            var mirrored=State(player:0,ball:new Vec3(0,1,-6),position:new Vec3(0,.85f,-6),velocity:new Vec3(0,2,-12),opponent:new Vec3(-1,.85f,8));
            Require(a.SequenceEqual(LearnedShotSelector.Observe(mirrored)),"canonical coordinates");
            var selector=new LearnedShotSelector(Model());var policy=new AiPolicy(Settings(Difficulty.Hard),Tuning,TryingSeed(Difficulty.Hard),selector);
            policy.Decide(State(phase:AiPhase.Paused));policy.Decide(State(online:true));policy.Decide(State(phase:AiPhase.WaitServe));Require(selector.Decisions==0,"inactive inference");
            var decision=ReachReaction(policy);Require(decision.ShouldSwing&&selector.Decisions==1,"learned return");
            policy.Decide(State(tick:100));Require(selector.Decisions==1,"duplicate inference for one ball");
        });
        Console.WriteLine($"ALL {passed} CHECKS PASSED");
    }
}
