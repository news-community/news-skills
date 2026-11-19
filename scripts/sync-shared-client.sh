#!/bin/sh
# Copy the canonical Local News API client into every skill that ships it.
#
# An installed skill has only its own folder, so meeting-prep and cite-check each carry
# a byte-identical copy of local_news_api.py and import its key handling, redirect guard
# and terms reader rather than re-implementing them. tests/test_skill_spec.py fails when
# a copy differs from the canonical file; this script is how to make it pass again.
#
#   sh scripts/sync-shared-client.sh
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
src="$root/skills/local-news-api/scripts/local_news_api.py"
for skill in meeting-prep cite-check; do
  dest="$root/skills/$skill/scripts/local_news_api.py"
  cp "$src" "$dest"
  echo "copied into skills/$skill/scripts/"
done
