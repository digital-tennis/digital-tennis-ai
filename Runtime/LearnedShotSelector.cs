using System;

namespace DigitalTennis.AI
{
    public interface IShotSelector
    {
        void Select(AiState state, out float widthFactor, out float depthFactor);
    }

    // Plain data shared by Unity JsonUtility and the offline training exporter.
    [Serializable]
    public sealed class PpoModelData
    {
        public int schema, inputSize, hiddenSize, actionCount, seed, steps;
        public string trainingTool;
        public float[] w1, b1, w2, b2, w3, b3, widthFactors, depthFactors;
    }

    /// <summary>Frozen SB3 PPO actor. No Python, network, Unity or mutable world state at inference time.</summary>
    public sealed class LearnedShotSelector : IShotSelector
    {
        public const int ObservationCount = 12;
        private readonly float[] w1, b1, w2, b2, w3, b3, widths, depths;
        public int Decisions { get; private set; }
        public int LastAction { get; private set; } = -1;
        public LearnedShotSelector(PpoModelData data)
        {
            if (data == null || data.schema != 1 || data.inputSize != ObservationCount ||
                data.hiddenSize != 32 || data.actionCount != 6 || data.steps < 1 || data.trainingTool != "stable-baselines3 PPO")
                throw new ArgumentException("Unsupported learned policy schema.");
            w1 = Copy(data.w1, 32 * ObservationCount); b1 = Copy(data.b1, 32);
            w2 = Copy(data.w2, 32 * 32); b2 = Copy(data.b2, 32);
            w3 = Copy(data.w3, 6 * 32); b3 = Copy(data.b3, 6);
            widths = Copy(data.widthFactors, 6); depths = Copy(data.depthFactors, 6);
            for (int i = 0; i < 6; i++)
                if (Math.Abs(widths[i]) > 1 || depths[i] < .2f || depths[i] > 1.4f)
                    throw new ArgumentException("Invalid learned action placement.");
        }
        private static float[] Copy(float[] values, int count)
        {
            if (values == null || values.Length != count) throw new ArgumentException("Invalid actor shape.");
            foreach (float v in values) if (!Numbers.Finite(v) || Math.Abs(v) > 100) throw new ArgumentException("Invalid actor weight.");
            return (float[])values.Clone();
        }
        public static float[] Observe(AiState state)
        {
            if (!state.IsValid) throw new ArgumentException("Invalid learned policy state.");
            float side = state.PlayerId == 1 ? 1 : -1;
            return new[] {
                state.BallPosition.X*side/BallPrediction.HalfWidth, state.BallPosition.Y/4,
                state.BallPosition.Z*side/BallPrediction.HalfLength,
                state.BallVelocity.X*side/30, state.BallVelocity.Y/30, state.BallVelocity.Z*side/30,
                state.OpponentPosition.X*side/BallPrediction.HalfWidth, state.OpponentPosition.Z*side/BallPrediction.HalfLength,
                state.PlayerPosition.X*side/BallPrediction.HalfWidth, state.PlayerPosition.Z*side/BallPrediction.HalfLength,
                state.ShotMultiplier/2, state.Gravity/30 };
        }
        private static float[] Layer(float[] input, float[] weights, float[] bias, bool tanh)
        {
            var output = new float[bias.Length];
            for (int row = 0; row < output.Length; row++)
            {
                double sum = bias[row];
                for (int col = 0; col < input.Length; col++) sum += weights[row * input.Length + col] * input[col];
                output[row] = tanh ? (float)Math.Tanh(sum) : (float)sum;
            }
            return output;
        }
        public int Predict(float[] observation)
        {
            if (observation == null || observation.Length != ObservationCount) throw new ArgumentException("Invalid observation shape.");
            foreach (float x in observation) if (!Numbers.Finite(x)) throw new ArgumentException("Non-finite observation.");
            var logits = Layer(Layer(Layer(observation, w1, b1, true), w2, b2, true), w3, b3, false);
            int action = 0;
            for (int i = 1; i < logits.Length; i++) if (logits[i] > logits[action]) action = i;
            return action;
        }
        public void Select(AiState state, out float widthFactor, out float depthFactor)
        {
            LastAction = Predict(Observe(state)); Decisions++;
            widthFactor = widths[LastAction]; depthFactor = depths[LastAction];
        }
    }
}
