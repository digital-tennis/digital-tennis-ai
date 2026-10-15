namespace DigitalTennis.AI
{
    /// <summary>Pure skill timing. The game still validates meter stock, phase and role.</summary>
    public static class AiSkillPolicy
    {
        public static bool ShouldActivate(AiState state, Difficulty difficulty, int stock, float remaining, bool justReturned)
        {
            DifficultySettings.For(difficulty);
            if (!state.IsValid || state.IsOnline || state.Phase != AiPhase.Rally || !justReturned ||
                stock < 1 || stock > 3 || !Numbers.Finite(remaining) || remaining != 0) return false;
            int threshold = difficulty == Difficulty.Easy ? 3 : difficulty == Difficulty.Medium ? 2 : 1;
            return stock >= threshold;
        }
    }
}
