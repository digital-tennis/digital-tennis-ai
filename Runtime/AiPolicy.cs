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

        private readonly AiTuning tuning;
        private readonly IShotSelector selector;
        public AiPolicy(DifficultySettings settings, AiTuning tuning, uint seed, IShotSelector selector = null)
        {
            Difficulty = settings.Difficulty; Settings = settings; this.tuning = tuning ?? throw new ArgumentNullException(nameof(tuning));
            // Reject the default struct, which has no valid skill threshold.
            if (settings.SkillStock < 1) throw new ArgumentException("Settings are required.");
            random = seed == 0 ? 0x6D2B79F5u : seed;
            this.selector = selector;
        }

        private float Next()
        {
            // xorshift32, explicit state: reproducible in .NET and Unity, independent of System.Random versions.
            random ^= random << 13; random ^= random >> 17; random ^= random << 5;
            return (random >> 8) / 16777216f;
        }

        public AiDecision Decide(AiState state)
        {
            Vec3 home = BallPrediction.Home(state.PlayerId, state.PlayerPosition.Y, tuning);
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
                target = BallPrediction.Clamp(BallPrediction.ContactTarget(state, tuning) + PositionError, state.PlayerId, state.PlayerPosition.Y, tuning);
            }
            elapsed += state.DeltaTime;
            if (elapsed + 0.000001f < Settings.ReactionSeconds)
                return new AiDecision(state.PlayerPosition, AiStatus.Reacting);
            if (attempted) return new AiDecision(target, AiStatus.AlreadySwung);
            if (!willTry) return new AiDecision(target, AiStatus.IntentionalMiss);
            bool ownSide = state.PlayerId == 1 ? state.BallPosition.Z > tuning.NetGap : state.BallPosition.Z < -tuning.NetGap;
            if (state.Phase != AiPhase.Rally || !ownSide || state.BounceCount >= 2 ||
                state.BallPosition.Y < tuning.MinHeight || state.BallPosition.Y > tuning.MaxHeight ||
                state.PlayerPosition.HorizontalDistance(state.BallPosition) > (state.Reach > 0 ? state.Reach : tuning.Reach))
                return new AiDecision(target, AiStatus.Tracking);
            attempted = true; Swings++;
            float facing = state.PlayerId == 0 ? 1f : -1f;
            AiStroke stroke = (state.BallPosition.X - state.PlayerPosition.X) * facing >= 0f ? AiStroke.Forehand : AiStroke.Backhand;
            return PlanShot(state, target, stroke);
        }

        private AiDecision PlanShot(AiState state, Vec3 moveTarget, AiStroke stroke)
        {
            // The old fixed powers overshoot from the service line. Solve speed for an actual in-court landing.
            float targetX = state.OpponentPosition.X >= 0f ? -tuning.TargetWidth : tuning.TargetWidth;
            float facing = state.PlayerId == 0 ? 1f : -1f;
            float targetZ = facing * tuning.TargetDepth;
            if (selector != null)
            {
                selector.Select(state, out float width, out float depth);
                targetX = -facing * width * tuning.TargetWidth;
                targetZ = facing * Numbers.Clamp(depth * tuning.TargetDepth, tuning.NetGap, BallPrediction.HalfLength);
            }
            float dz = Math.Max(1f, (targetZ - state.BallPosition.Z) * facing);
            float dx = (targetX - state.BallPosition.X) * facing;
            float yaw = Numbers.Clamp((float)Math.Atan2(dx, dz), -tuning.Yaw * (float)Math.PI / 180f, tuning.Yaw * (float)Math.PI / 180f);
            float distance = dz / (float)Math.Cos(yaw);
            double pitch = tuning.Pitch * Math.PI / 180d;
            double height = state.BallPosition.Y - state.Radius;
            double denominator = 2d * Math.Cos(pitch) * Math.Cos(pitch) * (height + distance * Math.Tan(pitch));
            float speed = denominator > 0d ? (float)Math.Sqrt(state.Gravity * distance * distance / denominator) : tuning.BaseSpeed;
            float power = Numbers.Clamp((speed / state.ShotMultiplier - tuning.BaseSpeed) / tuning.PowerSpeed, 0f, Settings.MaxPower);
            return new AiDecision(moveTarget, AiStatus.Swing, true, stroke, power,
                yaw * 180f / (float)Math.PI / tuning.Yaw, 0f);
        }
    }
}
