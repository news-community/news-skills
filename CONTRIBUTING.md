# Contributing

Thanks for looking. This repo shares tools that external Alaska creators can point at the
alaskanews.com public API. Contributions are welcome, with one hard rule and one habit.

## The hard rule: this stays read-only

`skills/alaska-desk` is a **consumer** client. It must never `PATCH`, `PUT` or `DELETE`, and its
only `POST` is the read-only `/rag/query`. Two things enforce that, and a change that trips either
will not be merged:

- `TestReadOnlyContract` in the test suite, which reads the source and fails on a write verb.
- A grep in CI, which runs even if the module fails to import (a test that cannot load is a test
  that cannot fail).

Publishing *into* the newsroom is a separate, editor-authenticated workflow. It does not belong
here, however convenient it would be.

## The habit: verify against the live API, and date it

This client consumes a platform that changes without telling us. Most of the defects found in the
2026-09-09 audit were not logic errors: they were claims that had quietly stopped being true.

So if you add or change a mode, or write anything about what an endpoint returns:

1. **Run it against the live API** and say so in the PR, with the date.
2. **Say which key you used.** "Works with my key" and "works with an external consumer key" are
   different claims, and only the second one describes this repo's audience. An elevated key can
   confirm that an endpoint exists and returns a given shape; it cannot confirm reach.
3. **Prefer a renderer that degrades.** Every mode falls back to raw JSON if a payload shape
   changes, and `--json` always returns the untouched payload. Keep it that way.
4. **Do not print a number the data does not support.** `/topics` returns `article_count: 0` for
   every beat; rendering that as "0 articles" would read as "no coverage exists", which is false.
   Suppress it and say why. The same reasoning applies to an empty result set from a mistyped
   corpus, which is why corpus names are validated before the request goes out.

## Running the tests

```bash
pip install pytest
python3 -m pytest skills/alaska-desk/scripts/test_alaska_desk.py -q
```

Offline: no key, no network. CI runs them on Python 3.9, 3.11 and 3.13.

A new mode needs, at minimum: a test that it is a GET, a next-steps entry so it is not a dead end
(`TestHateoasEmitted` will fail otherwise), and a rendering test. If you fix a defect, add the test
that would have caught it, and check that the test actually fails without your fix.

## Style

- The tool is Python 3, **standard library only**. A dependency needs a strong argument; "it would
  be tidier" is not one, because the install story for a community journalist is `git clone` and
  run.
- Every mode ends with next steps, related modes and a see-also. No dead ends, and errors carry a
  recovery path rather than just a status.
- Every output carries the source's usage terms. That is not decoration: the person running this is
  republishing someone else's reporting.
- No em dashes in prose or comments. Use commas, colons, parentheses, or two sentences.

## Reporting rather than fixing

If you would rather just tell us something is wrong, that is genuinely useful, especially
**"my key cannot reach X"**. Reach varies by role and we cannot see your key. Open an issue with the
output of `alaska_desk.py check`, which is safe to paste: it prints statuses, never your key.
