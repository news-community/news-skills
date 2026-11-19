# How this skill's access claims were verified

Provenance for the reach table and the honest-limits list in `SKILL.md`. Moved out of that file on
2026-09-10 because it is a record of *how we know*, not an instruction the agent needs on every run,
and the body an agent loads is budgeted (the spec recommends under 500 lines and 5,000 tokens).

**Read this when** you are about to change a claim in `SKILL.md` about what a key reaches, or when
you want to know how much weight a row in the reach table can carry.

## The two verification passes, and why they are not equivalent

**2026-07-23, a real external `cn_` consumer key.** Every mode was run: `digest`, `search`,
`article`, `transcript` and `events` returned and rendered correctly. `rag` returned 403.

**2026-09-09, an elevated newsroom key.** The modes were re-run. This re-confirms that each endpoint
exists, answers, and returns the shape the client renders. It says **nothing** about what a plain
external key reaches, which is what this repo's audience actually holds.

Those are different claims and the reach table is worded to keep them apart. An elevated key
confirms an endpoint's existence and shape; only an external key confirms external reach. Conflating
them is how the error below survived.

## A claim that was wrong, and how

An earlier version of the reach table asserted that a plain external key saw the
`external_documents` and `social_post` search corpora. The platform has gated both to editor/admin
since 2026-06-09, months before that table was written, so the line was describing either a
privileged key or a bug. It was removed rather than restated.

The lesson is the one in `CONTRIBUTING.md`: record which key produced a result, or the result cannot
be interpreted later.

## What `check` supersedes

`check` asks `GET /api/v1/me` for a `reachability` block the platform derives from its own router.
That is authoritative for *your* key in a way no table in a document can be, and it is why the
client stopped carrying a hand-written list of unreachable endpoints. Prefer running it over
trusting any table, including the one in `SKILL.md`.

## 2026-11-19: what was checked without a key, for 1.6.4 and 1.7.0

No key was available, so these are keyless checks plus the platform's code, and the rows they
support say so.

- **Public, verified keyless:** `/calendar` (200 with events), `/transcript/<id>/chunks` (404, not
  401, for an unknown id), `/tags/<slug>/articles` (200), `/persons/<id>/articles` (404, not 401) and
  `/feed/nearby` (200, 200 stories, every one with coordinates). `/persons/<id>/articles` answers
  without a key too, but only for a person with a public page (the platform's route), so `person`
  still sends the key; a keyless 404 for an unknown id does not show the route is fully public.
- **Keyed, verified keyless:** `/articles/<id>/clips` and `/transcript/<id>/clips` answer 401
  without a key. The platform's code checks only that the key covers the community. **Reach with an
  ordinary key is unverified**; the first person to run `clips` with one should record it here.
