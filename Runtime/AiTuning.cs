using System;
using System.Collections.Generic;
namespace DigitalTennis.AI
{
    /// <summary>Immutable rules supplied by the game's validated CSV bundle. No process-wide defaults.</summary>
    public sealed class AiTuning
    {
        public float HomeDepth { get; }
        public float MinDepth { get; }
        public float ContactHeight { get; }
        public float NetGap { get; }
        public float Reach { get; }
        public float MinHeight { get; }
        public float MaxHeight { get; }
        public float TargetWidth { get; }
        public float TargetDepth { get; }
        public float BaseSpeed { get; }
        public float PowerSpeed { get; }
        public float Yaw { get; }
        public float Pitch { get; }
        public AiTuning(IDictionary<string,float> values)
        {
            float Read(string key, float low, float high)
            {
                if (!values.TryGetValue(key,out float v) || !Numbers.Finite(v) || v < low || v > high)
                    throw new ArgumentException("Invalid AI tuning: " + key);
                return v;
            }
            HomeDepth = Read("move.home_depth",3f,11.885f);
            MinDepth = Read("move.min_depth",0.2f,3f);
            ContactHeight = Read("move.contact_height",0.2f,2.5f);
            NetGap = Read("hit.net_gap",0.05f,1f);
            Reach = Read("hit.reach",0.3f,3f);
            MinHeight = Read("hit.min_height",0.05f,1f);
            MaxHeight = Read("hit.max_height",1f,4f);
            TargetWidth = Read("ai.target_width",0f,4.115f);
            TargetDepth = Read("ai.target_depth",2f,11.885f);
            BaseSpeed = Read("shot.base_speed",2f,30f);
            PowerSpeed = Read("shot.power_speed",1f,30f);
            Yaw = Read("shot.yaw",1f,45f);
            Pitch = Read("shot.pitch",5f,45f);
            if (MinHeight >= MaxHeight || ContactHeight < MinHeight || ContactHeight > MaxHeight)
                throw new ArgumentException("AI contact heights are inconsistent.");
        }
    }
}
