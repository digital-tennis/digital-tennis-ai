#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export DOTNET_CLI_HOME="$repo_dir/.work/dotnet"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
cd "$repo_dir"
dotnet run --project tests/DigitalTennis.AI.Checks.csproj --configuration Release
