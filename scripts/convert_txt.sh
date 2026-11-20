#!/usr/bin/env bash
# Convert Football.TXT match files to JSON with the official openfootball tool.
#   gem install fbtxt2json
set -euo pipefail
cd "$(dirname "$0")/.."
command -v fbtxt2json >/dev/null || { echo "fbtxt2json missing: gem install fbtxt2json" >&2; exit 1; }
rm -rf build/json && mkdir -p build/json
find sources -name '*.txt' \
  -not -path 'sources/clubs/*' -not -path "sources/football.json/*" -not -path "sources/fc-*" -not -path '*/.git/*' \
  -not -path '*/squads/*' -not -path '*/archive/*' -not -name 'README*' -not -name 'NOTES*' \
  -not -name '.conf.txt' \
  | xargs -P "${JOBS:-8}" -I{} sh -c 'f="{}"; o="build/json/${f#sources/}"; o="${o%.txt}.json"; mkdir -p "$(dirname "$o")"; fbtxt2json "$f" -o "$o" >/dev/null 2>&1 || echo "skip (parse error): $f"'
echo "converted: $(find build/json -name '*.json' | wc -l) files"
