#!/usr/bin/env bash
# One command from a fresh clone to a deployed, verifiable token.
#
#   ./cpu_token/launch.sh              plan only — broadcasts nothing
#   ./cpu_token/launch.sh --confirm    deploy for real
#
# Installs what is missing, then hands over to launch.py.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bold=$'\033[1m'; dim=$'\033[2m'; red=$'\033[31m'; green=$'\033[32m'
yellow=$'\033[33m'; reset=$'\033[0m'

step() { printf '\n%s==>%s %s\n' "$bold" "$reset" "$1"; }
die()  { printf '\n%s%s%s\n\n' "$red" "$1" "$reset" >&2; exit 1; }

step "Checking prerequisites"
command -v node    >/dev/null 2>&1 || die "node is required (the Solidity compiler runs on it): https://nodejs.org"
command -v npm     >/dev/null 2>&1 || die "npm is required: it ships with node"
command -v python3 >/dev/null 2>&1 || die "python3 is required: https://python.org"
printf '  %s✓%s node %s, python %s\n' "$green" "$reset" "$(node -v)" "$(python3 -V | cut -d' ' -f2)"

step "Installing dependencies"
if [ ! -d node_modules/solc ] || [ ! -d node_modules/@openzeppelin/contracts ]; then
  echo "  installing solc + OpenZeppelin..."
  npm install --silent --no-fund --no-audit solc@0.8.24 @openzeppelin/contracts@5.0.2
else
  printf '  %s✓%s solc + OpenZeppelin already present\n' "$green" "$reset"
fi
python3 -c "import web3, eth_abi" 2>/dev/null || {
  echo "  installing web3..."
  python3 -m pip install --quiet web3 eth-abi requests
}
printf '  %s✓%s python packages ready\n' "$green" "$reset"

step "Checking configuration"
if [ ! -f .env ]; then
  cp cpu_token/launch/config.example.env .env
  printf '  %sCreated .env from the template.%s\n\n' "$yellow" "$reset"
  echo "  Fill in these before launching:"
  echo "    PRIVATE_KEY        deployer key (use a fresh wallet, funded only for this)"
  echo "    TREASURY_ADDRESS   receives the entire CPU supply"
  echo ""
  echo "  It defaults to ${bold}testnet${reset}. Rehearse there first — same script,"
  echo "  free coins, and a launch you have already done once."
  echo ""
  die "Edit .env, then run this again."
fi
printf '  %s✓%s .env present\n' "$green" "$reset"

step "Running the launcher"
exec python3 cpu_token/launch/launch.py --node-modules "$ROOT/node_modules" "$@"
