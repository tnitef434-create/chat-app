#!/usr/bin/env bash
# Clone / update the open data sources listed in scripts/sources.txt into ./sources
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p sources
grep -vE '^\s*(#|$)' scripts/sources.txt | while read -r repo dir; do
  if [ -d "sources/$dir/.git" ]; then
    echo "updating $repo"; git -C "sources/$dir" pull -q --ff-only
  else
    echo "cloning $repo"; git clone -q --depth 1 "https://github.com/$repo.git" "sources/$dir"
  fi
done
