using System;

namespace DigitalTennis.AI
{
    /// <summary>Seeded stateful policy. Call once per tick; never writes the world or sleeps.</summary>
    public sealed class AiPolicy
    {
        private uint random;
        private ulong incomingId;
        private long lastTick = -1;
        private bool attempted, willTry;
        private float elapsed;
        private Vec3 target;
        public Difficulty Difficulty { get; }
        public DifficultySettings Settings { get; }
        public int Samples { get; private set; }
        public int IntentionalMisses { get; private set; }
        public int Swings { get; private set; }
        public float ReactionElapsed => elapsed;
        public Vec3 PositionError { get; private set; }

        public AiPolicy(Difficulty difficulty, uint seed)
        {
            Difficulty = difficulty; Settings = DifficultySettings.For(difficulty);
            random = seed == 0 ? 0x6D2B79F5u : seed;
        }

        private float Next()
        {
            // xorshift32, explicit state: reproducible in .NET and Unity, independent of System.Random versions.
            random ^= random << 13; random ^= random >> 17; random ^= random << 5;
            return (random >> 8) / 16777216f;
        }

        public AiDecision Decide(AiState state)
        {
            Vec3 home = BallPrediction.Home(state.PlayerId, state.PlayerPosition.Y);
            if (state.IsOnline || state.Phase == AiPhase.Paused || state.Phase == AiPhase.WaitServe ||
                state.Phase == AiPhase.PointEnd || state.Phase == AiPhase.MatchEnd)
                return new AiDecision(home, AiStatus.Inactive);
            if (!state.IsValid || state.IncomingBallId == 0) return new AiDecision(home, AiStatus.Invalid);
            if (state.Tick <= lastTick) return new AiDecision(target.IsFinite ? target : home, AiStatus.Inactive);
            lastTick = state.Tick;
            if (!BallPrediction.IsIncoming(state)) return new AiDecision(home, AiStatus.Recovering);
            if (incomingId != state.IncomingBallId)
            {
                incomingId = state.IncomingBallId;
                elapsed = 0f; attempted = false; Samples++;
                float error = Settings.PositionError;
                PositionError = new Vec3((Next() * 2f - 1f) * error, 0f, (Next() * 2f - 1f) * error);
                willTry = Next() < Settings.SwingProbability;
                if (!willTry) IntentionalMisses++;
                target = BallPrediction.Clamp(BallPrediction.ContactTarget(state) + PositionError, state.PlayerId, state.PlayerPosition.Y);
            }
            elapsed += state.DeltaTime;
            if (elapsed + 0.000001f < Settings.ReactionSeconds)
                return new AiDecision(state.PlayerPosition, AiStatus.Reacting);
            if (attempted) return new AiDecision(target, AiStatus.AlreadySwung);
            if (!willTry) return new AiDecision(target, AiStatus.IntentionalMiss);
            bool ownSide = state.PlayerId == 1 ? state.BallPosition.Z > 0.2f : state.BallPosition.Z < -0.2f;
            if (state.Phase != AiPhase.Rally || !ownSide || state.BounceCount >= 2 ||
                state.BallPosition.Y < 0.2f || state.BallPosition.Y > 2.5f ||
                state.PlayerPosition.HorizontalDistance(state.BallPosition) > 1.5f)
                return new AiDecision(target, AiStatus.Tracking);
            attempted = true; Swings++;
            float facing = state.PlayerId == 0 ? 1f : -1f;
            AiStroke stroke = (state.BallPosition.X - state.PlayerPosition.X) * facing >= 0f ? AiStroke.Forehand : AiStroke.Backhand;
            return PlanShot(state, target, stroke);
        }

        private AiDecision PlanShot(AiState state, Vec3 moveTarget, AiStroke stroke)
        {
            // The old fixed powers overshoot from the service line. Solve speed for an actual in-court landing.
            float targetX = state.OpponentPosition.X >= 0f ? -2.5f : 2.5f;
            float facing = state.PlayerId == 0 ? 1f : -1f;
            float targetZ = facing * 8f;
            float dz = Math.Max(1f, (targetZ - state.BallPosition.Z) * facing);
            float dx = (targetX - state.BallPosition.X) * facing;
            float yaw = Numbers.Clamp((float)Math.Atan2(dx, dz), -25f * (float)Math.PI / 180f, 25f * (float)Math.PI / 180f);
            float distance = dz / (float)Math.Cos(yaw);
            double pitch = 20d * Math.PI / 180d;
            double height = state.BallPosition.Y - state.Radius;
            double denominator = 2d * Math.Cos(pitch) * Math.Cos(pitch) * (height + distance * Math.Tan(pitch));
            float speed = denominator > 0d ? (float)Math.Sqrt(state.Gravity * distance * distance / denominator) : 10f;
            float power = Numbers.Clamp((speed - 10f) / 12f, 0f, Settings.MaxPower);
            return new AiDecision(moveTarget, AiStatus.Swing, true, stroke, power,
                yaw * 180f / (float)Math.PI / 25f, 0f);
        }
    }
}
