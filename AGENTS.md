# Digital Tennis AI

- Keep the AI independent of UnityEngine, game assemblies, scene objects and transport. Runtime is a netstandard2.1 library and the same source is a Unity package.
- Preserve NU40-DK plus separately attached external IMU, and the 12-day / three-developer plan.
- AI returns decisions only. Game adapters must apply movement limits and pass swings through the ordinary RacketInput gate.
- Use explicit seeded random state, tick/delta-time reaction delays and one random sample set / swing per incoming ball. Pause, online mode, point end and match end must not progress decisions.
- Run `dotnet run --project tests/DigitalTennis.AI.Checks.csproj --configuration Release` before publishing. Keep numerical results separate from Unity or physical controller evidence.
- Publish changes in feature branches and draft PRs. Squash approved merges and delete merged remote and local branches.
- Do not commit bin, obj or .work. Generate Unity .meta files with stable unique GUIDs and preserve them.
