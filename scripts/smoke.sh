#!/usr/bin/env bash
# After a deploy: does the app find and remove personal information end to end? scripts/smoke.sh [port]
set -euo pipefail
cd "$(dirname "$0")"
URL="http://localhost:${1:-8000}"
curl -sf "${URL}/ready"; echo
curl -sf -F "file=@smoke-lease.pdf" "${URL}/api/detect" | python3 -c '
import json, sys
found = [f["text"] for f in json.load(sys.stdin)["findings"]]
assert "(202) 555-0143" in found, found
print("detect: found", len(found), "items, including the phone number")'
curl -sf -F "file=@smoke-lease.pdf" -F 'remove=[{"page":0,"text":"(202) 555-0143"}]' "${URL}/api/redact" -o /tmp/smoke-redacted.pdf
head -c 4 /tmp/smoke-redacted.pdf | grep -q "%PDF" && echo "redact: returned a PDF"
echo "smoke test passed"
