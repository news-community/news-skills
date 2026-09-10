---
name: My key cannot reach something
about: A mode returns 401/403, or returns nothing when you expected coverage
title: "reach: <mode> returns <status>"
labels: reach
---

Reach varies by API-key role and we cannot see your key, so the output of `check` is the single most
useful thing you can paste. It prints statuses only, never your key.

**Output of `python3 skills/news-desk/scripts/news_desk.py check`:**

```
paste here
```

**The command that failed, and what it printed:**

```
paste here (redact anything you would rather not share)
```

**What you expected instead:**

<!-- e.g. "search found this story, so browse --tag should list it too" -->

**Before you file:** some endpoints authenticate by browser session only and reject *every* API
key, including an admin's, so no role upgrade reaches them. They answer 403 with
`error: session_auth_only`. `check` lists them, straight from the platform rather than from a list
kept by hand here, under "Not reachable by ANY api key". If your endpoint is in that list, it is
working as designed and there is nothing to file.
