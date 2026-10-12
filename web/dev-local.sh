#!/bin/bash
# Local test of the site: exports the runner data from Supabase (needs
# SUPABASE_SERVICE_ROLE_KEY in .env.local), builds the same static site
# Cloudflare serves, and serves it on port 3000.
# Open http://localhost:3000 on this computer, or the address printed below on
# a phone on the same Wi-Fi.
cd "$(dirname "$0")"
node scripts/export-static.mjs || exit 1
npm run build || exit 1
echo ""
echo "  On this computer:  http://localhost:3000"
echo "  On a phone:        http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | cut -d' ' -f1):3000   (same Wi-Fi)"
echo ""
echo "  Stop with Ctrl+C"
exec python3 -m http.server 3000 --bind 0.0.0.0 --directory out
