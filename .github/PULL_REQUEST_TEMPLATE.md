## What this changes

<!-- One or two sentences. -->

## Checklist

- [ ] `python3 -m pytest skills/news-desk/scripts/test_news_desk.py -q` passes.
- [ ] Still read-only: no `PATCH`/`PUT`/`DELETE`, and no new `POST` beyond `/rag/query`.
- [ ] If this fixes a defect, I added the test that would have caught it, and checked it **fails**
      without the fix.
- [ ] If this adds a mode: it has next steps (so it is not a dead end), a rendering test, and it
      falls back to raw JSON on an unexpected shape.

## If this touches the API surface

- **Ran live on** (date):
- **Key used** (external consumer key / elevated key / no key):
      <!-- An elevated key confirms an endpoint exists and returns a shape. It does NOT confirm
           what an external consumer key can reach, which is what this repo's audience has. -->
- **What the API actually returned** (paste or summarise):
