using System;

namespace DigitalTennis.AI
{
    public readonly struct LandingPrediction
    {
        public readonly bool Valid;
        public readonly float TimeToBounce;
        public readonly Vec3 Position;
        public LandingPrediction(bool valid, float time, Vec3 position) { Valid = valid; TimeToBounce = time; Position = position; }
    }

    public static class BallPrediction
    {
        public const float HalfWidth = 4.115f, HalfLength = 11.885f;
        public static LandingPrediction Landing(Vec3 position, Vec3 velocity, float gravity = 9.81f, float plane = 0f,
            bool stopped = false)
        {
            if (stopped || !position.IsFinite || !velocity.IsFinite || !Numbers.Finite(gravity) || gravity <= 0f ||
                !Numbers.Finite(plane) || position.Y < plane) return default;
            double discriminant = (double)velocity.Y * velocity.Y + 2d * gravity * (position.Y - plane);
            double time = (velocity.Y + Math.Sqrt(discriminant)) / gravity;
            if (double.IsNaN(time) || time <= 0d || time > 3d) return default;
            var at = new Vec3(position.X + velocity.X * (float)time, plane, position.Z + velocity.Z * (float)time);
            return at.IsFinite ? new LandingPrediction(true, (float)time, at) : default;
        }
        public static Vec3 Home(int player, float y) => new Vec3(0f, Numbers.Finite(y) ? y : 0.85f, player == 1 ? 8f : -8f);
        public static Vec3 Clamp(Vec3 target, int player, float y)
        {
            float side = player == 1 ? 1f : -1f;
            return new Vec3(Numbers.Clamp(target.X, -HalfWidth, HalfWidth), y,
                side * Numbers.Clamp(target.Z * side, 0.8f, HalfLength));
        }
        public static bool IsIncoming(AiState state)
        {
            float ownSide = state.PlayerId == 1 ? 1f : -1f;
            return state.HasBall && !state.IsStopped && state.LastHitter != state.PlayerId &&
                state.BallVelocity.Z * ownSide > 0.01f;
        }
        public static Vec3 ContactTarget(AiState state)
        {
            Vec3 home = Home(state.PlayerId, state.PlayerPosition.Y);
            if (!state.IsValid || !IsIncoming(state)) return home;
            if (state.BounceCount >= 1) return Clamp(state.BallPosition, state.PlayerId, state.PlayerPosition.Y);
            var landing = Landing(state.BallPosition, state.BallVelocity, state.Gravity, state.Radius, state.IsStopped);
            if (!landing.Valid) return home;
            // Aim for the rising ball at 1m after the first ground bounce, using the game's physical coefficients.
            double impactY = state.BallVelocity.Y - state.Gravity * landing.TimeToBounce;
            double rebound = -impactY * state.BounceRestitution;
            double discriminant = rebound * rebound - 2d * state.Gravity * Math.Max(0d, 1d - state.Radius);
            double rise = discriminant >= 0d ? (rebound - Math.Sqrt(discriminant)) / state.Gravity : 0d;
            if (rise < 0d || landing.TimeToBounce + rise > 3d) rise = 0d;
            Vec3 contact = landing.Position + new Vec3(state.BallVelocity.X, 0f, state.BallVelocity.Z) *
                (state.SpeedRetention * (float)rise);
            return Clamp(contact, state.PlayerId, state.PlayerPosition.Y);
        }
    }
}
