#!/bin/sh
# Vercel's install step for the hosted site. Fetches one pinned commit of the
# public repo, puts the landing page at / and the dashboard at /app/, then
# copies the bot's code beside api/bot.py, then installs exactly what the landing
# page's lockfile lists. See docs/hosting.md.
set -eu
SHA="__COMMIT_SHA__"
URL="https://codeload.github.com/MeagerPotato/ilumina/tar.gz/$SHA"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$URL" -o src.tgz
else
  node -e "fetch(process.argv[1]).then(async (r) => { if (!r.ok) throw new Error('HTTP ' + r.status); require('fs').writeFileSync('src.tgz', Buffer.from(await r.arrayBuffer())); })" "$URL"
fi
mkdir -p .src
tar -xzf src.tgz -C .src
cp -R .src/*/landing/. .
# Vite copies public/ into dist/, so the dashboard is served at /app/.
mkdir -p public/app
cp -R .src/*/dashboard/. public/app/
# The bot's code, beside api/bot.py, for the Python function.
cp .src/*/bot.py .
cp -R .src/*/ilumina .
rm -rf .src src.tgz
npm ci
