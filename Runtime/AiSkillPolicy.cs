namespace DigitalTennis.AI
{
    /// <summary>Pure skill timing. The game still validates meter stock, phase and role.</summary>
    public static class AiSkillPolicy
    {
        public static bool ShouldActivate(AiState state, DifficultySettings settings, int stock, float remaining, bool justReturned)
        {
            if (!state.IsValid || state.IsOnline || state.Phase != AiPhase.Rally || !justReturned ||
                stock < 1 || stock > 3 || !Numbers.Finite(remaining) || remaining != 0) return false;
            int threshold = settings.SkillStock;
            return threshold >= 1 && threshold <= 3 && stock >= threshold;
        }
    }
}
