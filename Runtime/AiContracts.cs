using System;

namespace DigitalTennis.AI
{
    public enum Difficulty { Easy, Medium, Hard }
    public enum AiPhase { WaitServe, ServeInFlight, Rally, PointEnd, MatchEnd, Paused }
    public enum AiStroke { Forehand = 1, Backhand = 2 }
    public enum AiStatus { Inactive, Invalid, Recovering, Reacting, Tracking, IntentionalMiss, Swing, AlreadySwung }

    public readonly struct Vec3
    {
        public readonly float X, Y, Z;
        public Vec3(float x, float y, float z) { X = x; Y = y; Z = z; }
        public bool IsFinite => Numbers.Finite(X) && Numbers.Finite(Y) && Numbers.Finite(Z);
        public static Vec3 operator +(Vec3 a, Vec3 b) => new Vec3(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
        public static Vec3 operator *(Vec3 a, float scale) => new Vec3(a.X * scale, a.Y * scale, a.Z * scale);
        public float HorizontalDistance(Vec3 other) => (float)Math.Sqrt((X-other.X)*(X-other.X) + (Z-other.Z)*(Z-other.Z));
        public override string ToString() => FormattableString.Invariant($"({X:F4},{Y:F4},{Z:F4})");
    }

    public readonly struct DifficultySettings
    {
        public readonly float ReactionSeconds, PositionError, SwingProbability, MaxPower;
        private DifficultySettings(float reaction, float error, float probability, float power)
        { ReactionSeconds = reaction; PositionError = error; SwingProbability = probability; MaxPower = power; }
        public static DifficultySettings For(Difficulty difficulty)
        {
            switch (difficulty)
            {
                case Difficulty.Easy: return new DifficultySettings(0.35f, 1.5f, 0.65f, 0.50f);
                case Difficulty.Medium: return new DifficultySettings(0.20f, 0.8f, 0.85f, 0.65f);
                case Difficulty.Hard: return new DifficultySettings(0.10f, 0.25f, 0.95f, 0.80f);
                default: throw new ArgumentOutOfRangeException(nameof(difficulty));
            }
        }
    }

    /// <summary>Immutable world-space snapshot. Tick is a monotonic policy-update counter, not a shot-local ball tick.</summary>
    public readonly struct AiState
    {
        public readonly long Tick;
        public readonly float DeltaTime;
        public readonly int PlayerId, LastHitter;
        public readonly Vec3 PlayerPosition, OpponentPosition, BallPosition, BallVelocity;
        public readonly AiPhase Phase;
        public readonly int BounceCount;
        public readonly ulong IncomingBallId;
        public readonly bool HasBall, IsStopped, IsOnline;
        public readonly float Gravity, Radius, BounceRestitution, SpeedRetention;

        public AiState(long tick, float dt, int playerId, Vec3 playerPosition, Vec3 opponentPosition,
            Vec3 ballPosition, Vec3 ballVelocity, AiPhase phase, int bounceCount, ulong incomingBallId,
            int lastHitter, bool hasBall = true, bool isStopped = false, bool isOnline = false,
            float gravity = 9.81f, float radius = 0.12f, float bounceRestitution = 0.7f, float speedRetention = 0.96f)
        {
            Tick = tick; DeltaTime = dt; PlayerId = playerId; PlayerPosition = playerPosition;
            OpponentPosition = opponentPosition; BallPosition = ballPosition; BallVelocity = ballVelocity;
            Phase = phase; BounceCount = bounceCount; IncomingBallId = incomingBallId; LastHitter = lastHitter;
            HasBall = hasBall; IsStopped = isStopped; IsOnline = isOnline; Gravity = gravity; Radius = radius;
            BounceRestitution = bounceRestitution; SpeedRetention = speedRetention;
        }
        public bool IsValid => Tick >= 0 && Numbers.Finite(DeltaTime) && DeltaTime > 0f && DeltaTime <= 1f &&
            (PlayerId == 0 || PlayerId == 1) && (LastHitter == 0 || LastHitter == 1) &&
            PlayerPosition.IsFinite && OpponentPosition.IsFinite && BallPosition.IsFinite && BallVelocity.IsFinite &&
            Enum.IsDefined(typeof(AiPhase), Phase) && BounceCount >= 0 && BounceCount <= 2 &&
            Numbers.Finite(Gravity) && Gravity > 0f && Numbers.Finite(Radius) && Radius > 0f &&
            Numbers.Finite(BounceRestitution) && BounceRestitution >= 0f && BounceRestitution <= 1f &&
            Numbers.Finite(SpeedRetention) && SpeedRetention >= 0f && SpeedRetention <= 1f;
    }

    public readonly struct AiDecision
    {
        public readonly Vec3 MoveTarget;
        public readonly bool ShouldSwing;
        public readonly AiStroke Stroke;
        public readonly float Power01, AimX, AimZ;
        public readonly AiStatus Status;
        public AiDecision(Vec3 target, AiStatus status, bool swing = false, AiStroke stroke = AiStroke.Forehand,
            float power = 0f, float aimX = 0f, float aimZ = 0f)
        { MoveTarget = target; Status = status; ShouldSwing = swing; Stroke = stroke; Power01 = power; AimX = aimX; AimZ = aimZ; }
        public override string ToString() => FormattableString.Invariant($"{MoveTarget}|{Status}|{ShouldSwing}|{Stroke}|{Power01:F6}|{AimX:F6}|{AimZ:F6}");
    }

    internal static class Numbers
    {
        public static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);
        public static float Clamp(float value, float low, float high) => Math.Max(low, Math.Min(high, value));
    }
}
