#!/bin/bash
# Local test of the site with the live Željava settings: builds the same
# static site Cloudflare serves, then serves it on port 3000.
# Open http://localhost:3000 on this Mac, or the address printed below on a
# phone connected to the same Wi-Fi.
cd "$(dirname "$0")"
# ./dev-local.sh zagreb   → the Zagreb site with its own settings (events/zagreb-2026.env)
if [ "$1" = "zagreb" ]; then
  EVENT=zagreb-2026 npm run build || exit 1
  mkdir -p out/data
  [ -f out/data/stats.json ] || echo '{"ok":true,"photos":0,"finishers":0,"tagged_bibs":0}' > out/data/stats.json
  rm -f .env.production.local
  echo ""
  echo "  On this Mac:  http://localhost:3000"
  echo "  On a phone:   http://$(ipconfig getifaddr en0 2>/dev/null || echo 'YOUR-MAC-IP'):3000   (same Wi-Fi)"
  echo ""
  echo "  Stop with Ctrl+C"
  exec python3 -m http.server 3000 --bind 0.0.0.0 --directory out
fi
set -a; source .env.demo; set +a
export NEXT_PUBLIC_EVENT_THEME=zeljava
export NEXT_PUBLIC_BRAND_MARK=/brand/zeljava-logo.png
export NEXT_PUBLIC_BRAND_MARK_RATIO="606 / 313"
export NEXT_PUBLIC_BRAND_ICON=/brand/zeljava-icon-32.png
export NEXT_PUBLIC_HERO_IMAGE=/media/zeljava-2026/w/9f095ded287cb4d969d14618.jpg
export NEXT_PUBLIC_TURNSTILE_SITEKEY=
npx next build || exit 1
echo ""
echo "  On this Mac:  http://localhost:3000"
echo "  On a phone:   http://$(ipconfig getifaddr en0 2>/dev/null || echo 'YOUR-MAC-IP'):3000   (same Wi-Fi)"
echo ""
echo "  Stop with Ctrl+C"
python3 -m http.server 3000 --bind 0.0.0.0 --directory out
