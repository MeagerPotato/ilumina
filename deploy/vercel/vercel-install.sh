#!/bin/sh
# Vercel's install step for the hosted site. Fetches one pinned commit of the
# public repo, puts the landing page at / and the dashboard at /app/, then
# installs exactly what the landing page's lockfile lists. The bot's Python
# files are uploaded with the deployment itself (see docs/hosting.md), because
# Vercel builds the Python function from the uploaded files.
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
rm -rf .src src.tgz
npm ci
