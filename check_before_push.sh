#!/usr/bin/env bash
# Run from the repository root before every push:
#   1. secrets: API keys, tokens, key-bearing URLs, e-mail addresses, home paths;
#   2. size: files over 50 MB (GitHub warns) and 100 MB (GitHub refuses);
#   3. what git would actually commit (tracked + staged), so ignored data does not slip in.
set -uo pipefail
cd "$(dirname "$0")"
echo "== 1. secrets / identifying strings in tracked or untracked-but-not-ignored files"
PATTERN='hypersync_[A-Za-z0-9]{8,}|nodereal\.io/v1/[A-Za-z0-9]{16,}|alchemy\.com/v2/[A-Za-z0-9_-]{16,}|api[_-]?key *[=:] *["'"'"']?[A-Za-z0-9]{12,}|ENVIO_API_TOKEN *= *["'"'"']?[A-Za-z0-9]{8,}|Bearer [A-Za-z0-9._-]{16,}|@[a-z0-9.-]+\.(com|edu|org|cn|net)|/Users/[a-z]+|C:\\\\Users'
git ls-files --cached --others --exclude-standard -z | xargs -0 grep -EIn "$PATTERN" 2>/dev/null | grep -vE '<token|<key>|=\.\.\.|REPL_ROOT|example\.com' | head -40
echo "   (nothing above = clean)"
echo "== 2. files over 50 MB among what git would track, and the total"
git ls-files --cached --others --exclude-standard -z | python3 -c '
import os, sys
fs = [f for f in sys.stdin.buffer.read().split(b"\0") if f]
sizes = [(os.path.getsize(f), f.decode()) for f in fs if os.path.exists(f)]
for s, f in sorted(sizes, reverse=True):
    if s > 50 * 1048576:
        print(f"   {s/1048576:7.1f} MB  {f}  <-- GitHub refuses files over 100 MB")
print(f"   files: {len(sizes)}   total: {sum(s for s, _ in sizes)/1048576:.1f} MB   largest: {max(sizes)[0]/1048576:.1f} MB")
'
echo "   (no file listed = nothing near the 100 MB limit)"
echo "== 3. ignored data present locally (never committed)"
git status --ignored --short | grep '^!!' | head -20
