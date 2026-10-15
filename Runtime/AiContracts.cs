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
        public readonly Difficulty Difficulty;
        public readonly int SkillStock;
        public DifficultySettings(Difficulty difficulty, float reaction, float error, float probability, float power, int skillStock)
        {
            if (!Enum.IsDefined(typeof(Difficulty),difficulty) || !Numbers.Finite(reaction) || reaction < 0 || reaction > 1 ||
                !Numbers.Finite(error) || error < 0 || error > 3 || !Numbers.Finite(probability) || probability < 0 || probability > 1 ||
                !Numbers.Finite(power) || power < 0 || power > 1 || skillStock < 1 || skillStock > 3)
                throw new ArgumentOutOfRangeException(nameof(difficulty), "Invalid difficulty settings.");
            Difficulty = difficulty; ReactionSeconds = reaction; PositionError = error; SwingProbability = probability;
            MaxPower = power; SkillStock = skillStock;
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
        public readonly float Gravity, Radius, BounceRestitution, SpeedRetention, Reach, ShotMultiplier;

        public AiState(long tick, float dt, int playerId, Vec3 playerPosition, Vec3 opponentPosition,
            Vec3 ballPosition, Vec3 ballVelocity, AiPhase phase, int bounceCount, ulong incomingBallId,
            int lastHitter, bool hasBall = true, bool isStopped = false, bool isOnline = false,
            float gravity = float.NaN, float radius = float.NaN, float bounceRestitution = float.NaN, float speedRetention = float.NaN, float reach = 0, float shotMultiplier = 1)
        {
            Tick = tick; DeltaTime = dt; PlayerId = playerId; PlayerPosition = playerPosition;
            OpponentPosition = opponentPosition; BallPosition = ballPosition; BallVelocity = ballVelocity;
            Phase = phase; BounceCount = bounceCount; IncomingBallId = incomingBallId; LastHitter = lastHitter;
            HasBall = hasBall; IsStopped = isStopped; IsOnline = isOnline; Gravity = gravity; Radius = radius;
            BounceRestitution = bounceRestitution; SpeedRetention = speedRetention; Reach=reach;ShotMultiplier=shotMultiplier;
        }
        public bool IsValid => Tick >= 0 && Numbers.Finite(DeltaTime) && DeltaTime > 0f && DeltaTime <= 1f &&
            (PlayerId == 0 || PlayerId == 1) && (LastHitter == 0 || LastHitter == 1) &&
            PlayerPosition.IsFinite && OpponentPosition.IsFinite && BallPosition.IsFinite && BallVelocity.IsFinite &&
            Enum.IsDefined(typeof(AiPhase), Phase) && BounceCount >= 0 && BounceCount <= 2 &&
            Numbers.Finite(Gravity) && Gravity > 0f && Numbers.Finite(Radius) && Radius > 0f &&
            Numbers.Finite(BounceRestitution) && BounceRestitution >= 0f && BounceRestitution <= 1f &&
            Numbers.Finite(Reach) && Reach >= 0 && Numbers.Finite(ShotMultiplier) && ShotMultiplier > 0 &&
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
