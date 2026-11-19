# Working the story: the five Ws (the `angles` mode)

Moved out of `SKILL.md` on 2026-11-19 to keep the body an agent loads on every run inside its budget.

**Read this when** you are choosing an `angles --intent`.

Treat Who, What, When, Where, Why as five independent axes. The investigative method has two modes,
and they land on opposite sides of this tool's read-only line:

- **Matching** (ranking which stories are genuinely related) is axis-weighted similarity. That is
  the **server's** job; it happens inside `/search` and `/rag/query`. This client does not re-do it.
- **Discovery** (fix two Ws, expand the rest) is a workflow of chained searches, and that is exactly
  what a sourcing tool can scaffold. It is what `angles` runs.

`angles --intent` names which two Ws you fix:

| Intent (the two Ws it fixes) | `--intent` | Runs now: one `/search` over | Suggested next |
|---|---|---|---|
| similar stories (What + Why) | `similar` | articles | `rag` to hold What+Why and vary When |
| historical precedent (What + Why) | `precedent` | articles, transcripts | `--until` an earlier year |
| track a company or agency (Who + What) | `track` | articles, transcripts | the actor across more years |
| local coverage (Where + What) | `local` | articles, events, transcripts | `--community <slug>` is the Where |
| same narrative angle (Why + What) | `angle` | articles | `rag` on who is using the framing |

Each run is **one** `/search`; everything in the last column is a Next step you choose to run, so you
drive the depth, not the key's rate limit.
