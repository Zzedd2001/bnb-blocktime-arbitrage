#!/usr/bin/env bash
# Greps the package for author-identifying strings and credentials before upload.  Add your own name, e-mail,
# institution and user name to the pattern below; the script prints every hit (an empty output is the goal).
cd "$(dirname "$0")"
PATTERN='@[a-z0-9.-]+\.(com|edu|org|cn|net)|/Users/|/home/[a-z]+|C:\\\\Users|api[_-]?key *[=:]|ENVIO_API_TOKEN *=|nodereal\.io/v1/|Authorization: Bearer'
grep -rEIn --exclude=check_anonymity.sh --exclude-dir=.git "$PATTERN" . | grep -v 'REPL_ROOT' | grep -vE '<token|<key>|=\.\.\.' | head -50
echo "--- done (no lines above = nothing found)"
