using System;

namespace DigitalTennis.AI
{
    [Serializable] public sealed class FullMatchModelData
    {
        public int schema, observationVersion, actionVersion, rewardVersion, inputSize, hiddenSize, actionCount, steps;
        public string trainingTool;
        public float[] w1,b1,w2,b2,w3,b3;
    }
    /// <summary>Frozen full-match tactical actor; independent netstandard2.1 inference.</summary>
    public sealed class FullMatchActor
    {
        public const int ObservationVersion=2, ActionVersion=1, RewardVersion=1, ObservationCount=32;
        // Canonical self is at positive z; the game adapter maps stable identities and physical ends.
        public static readonly string[] Fields={"ballX","ballY","ballZ","velocityX","velocityY","velocityZ","opponentX","opponentZ","selfX","selfZ","shotMultiplier","gravity",
            "selfPoints","opponentPoints","selfGames","opponentGames","selfSets","opponentSets","selfServing","tieBreak","phase","bounces","selfEnergy","opponentEnergy","selfStock","opponentStock","selfBuff","opponentBuff","selfCharacter","opponentCharacter","selfAtFarEnd","faults"};
        private static readonly float[] scales={4.115f,4,11.885f,30,30,30,4.115f,11.885f,4.115f,11.885f,2,30,7,7,6,6,2,2,1,1,4,2,100,100,3,3,10,10,14,14,1,2};
        readonly float[] w1,b1,w2,b2,w3,b3;
        public FullMatchActor(FullMatchModelData d)
        {
            if(d==null||d.schema!=1||d.observationVersion!=ObservationVersion||d.actionVersion!=ActionVersion||d.rewardVersion!=RewardVersion||d.inputSize!=32||d.hiddenSize!=32||d.actionCount!=6||d.steps<1||d.trainingTool!="stable-baselines3 PPO")throw new ArgumentException("Unsupported full-match actor");
            w1=Copy(d.w1,1024);b1=Copy(d.b1,32);w2=Copy(d.w2,1024);b2=Copy(d.b2,32);w3=Copy(d.w3,192);b3=Copy(d.b3,6);
        }
        static float[] Copy(float[] v,int n)
        {
            if(v==null||v.Length!=n)throw new ArgumentException("Actor shape");
            foreach(float x in v)if(!Numbers.Finite(x)||Math.Abs(x)>100)throw new ArgumentException("Actor nonfinite/range");
            return (float[])v.Clone();
        }
        public static float[] Normalize(float[] raw)
        {
            if(raw==null||raw.Length!=32)throw new ArgumentException("Observation shape");
            var o=new float[32];for(int i=0;i<32;i++){if(!Numbers.Finite(raw[i]))throw new ArgumentException("Observation nonfinite");o[i]=Numbers.Clamp(raw[i]/scales[i],-2,2);}return o;
        }
        static float[] Layer(float[] x,float[] w,float[] b,bool tanh)
        {
            var y=new float[b.Length];for(int r=0;r<y.Length;r++){double s=b[r];for(int c=0;c<x.Length;c++)s+=w[r*x.Length+c]*x[c];y[r]=tanh?(float)Math.Tanh(s):(float)s;}return y;
        }
        public float[] Logits(float[] o)
        {
            if(o==null||o.Length!=32)throw new ArgumentException("Observation shape");
            foreach(float x in o)if(!Numbers.Finite(x)||Math.Abs(x)>2)throw new ArgumentException("Observation range");
            return Layer(Layer(Layer(o,w1,b1,true),w2,b2,true),w3,b3,false);
        }
        public int Predict(float[] o){var l=Logits(o);int a=0;for(int i=1;i<6;i++)if(l[i]>l[a])a=i;return a;}
        public static void Placement(int action,out float width,out float depth)
        {
            if(action<0||action>=6)throw new ArgumentOutOfRangeException(nameof(action));
            width=action%3-1;depth=action<3?.55f:1f;
        }
    }
}
