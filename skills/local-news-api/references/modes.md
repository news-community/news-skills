# Dates, `events`, `near`, `clips` and `person`: how they work and where they stop

**Parent:** [`SKILL.md`](../SKILL.md) · **Siblings:** [angles](angles.md) · [output](output.md) · [verification](verification.md)

Moved out of `SKILL.md` on 2026-11-19 to keep the body an agent loads on every run inside its budget.

**Read this when** you filter by date, list upcoming events, look for stories near a place, need
clip ids, or attribute words to someone `person` lists.

**The When axis: `--since` / `--until`.** `search` and `angles` both take `--since YYYY-MM-DD` and
`--until YYYY-MM-DD`, which map to the API's `date_from` / `date_to` on the articles corpus. This is
the only one of the five Ws the server can filter on, and it is the axis the `angles` intents talk
about holding or expanding, so `--intent precedent --until 2020-01-01` is how you actually ask the
question that intent describes. Result lines carry the date for the same reason: you cannot check
the two-axis relevance rule below against results whose dates are hidden.

**`events` is forward-looking.** It reads `GET /calendar`, whose window starts now and runs 30 days
(`--days` to change it, `--type meeting|public_notice|community_event|class` to narrow), so it never
lists a past meeting as upcoming. To search events by relevance across all time, including past ones,
use `search "<q>" --corpus events`. `/calendar` has no full-text parameter, so a query argument to
`events` filters the window client-side on title and location. The calendar stores times in UTC, so
`events` shows each in the newsroom's own time zone, labelled (`--tz` overrides), and an all-day
entry as a date.

## `--since` on `browse` and `person`

`/articles`, `/tags/<slug>/articles` and `/persons/<id>/articles` take no date, so `--since` reads them
newest-first and keeps every story published on or after the day. Those lists are ordered by
**arrival**, which is publication pulled back by up to 24 hours when a story's source is old, so a
qualifying story can sit below a whole page of older ones. Paging therefore stops once a page's
oldest arrival is more than 24 hours before the day, when nothing later can qualify (on a route that
reports no arrival time, at the first page with nothing new). It stops after 1,000 stories and says so.
The day is counted in the newsroom's own time zone, as `digest --date` counts it; `--tz` overrides.
`browse --since` needs `--sort new` (the default), since no other order lets it know when to stop.
`browse --tag` needs no key. The tag route takes no community, so `--community` does not narrow
it: without a key it reads the newsroom at the configured site. `person` sends one for both its calls: the coverage route answers
without a key only for people with a public page, and a key reaches the rest.

## `near LAT,LON`

Reads `GET /feed/nearby` (public): the newsroom's newest published stories, about 200, each with
coordinates, unsorted. The client sorts them by distance from the point you give and shows miles;
`--radius MILES` keeps only those inside it. **It covers only that pool** (on 2026-11-19, two days of
stories), and says what span it covered; use `search` for anything older.

- **It takes coordinates, never a place name.** Resolving a name through the platform's `/places`
  would cost the newsroom a geocoding lookup on every run.
- **Statewide stories are listed apart.** A story about the whole newsroom area sits on one central
  point whose location is the area's own name (28 of 200 on 2026-11-19). Ranked by distance, it would
  look local to whoever lives near the centre, so it is listed separately without a distance.
- A latitude south of the equator starts with `-`: write `near -- -33.87,151.21`.
- `/articles?sort=nearby` was not used: with a key it also folds in the key owner's saved locations,
  so its answer would depend on whose key ran it.

## `clips --article <id>` / `clips --transcript <id>`

`GET /clips` (browse) refuses every API key, so a script could download any clip and could not ask
which existed. The platform added `/articles/<id>/clips` and `/transcript/<id>/clips` on 2026-09-10 to
close that gap. Each clip carries its quote, the speaker, where it starts in the meeting and a public
download URL. The duration shown is the quote's; the file runs a few seconds longer, padded so it does
not start or end mid-word.

**Reach:** both answer 401 without a key (checked 2026-11-19), and the platform's code checks only
that the key covers the community, with no role. That is what the code permits; **no ordinary key
has run it yet**, so treat the reach row as unverified until one does (see `verification.md`).

## `person`: appears in, not quoted in

The distinction is load-bearing. `/persons/<id>/articles` returns a UNION: articles where an attribution matched the person's name,
and articles structurally linked to them. Only the first kind carries a verbatim excerpt. Rows with a
quote are marked `quoted (Nx)`; when a whole page has none, the client says so, because "Dunleavy
appears in this piece" and "Dunleavy said this in this piece" are different claims and only one of
them is quotable. Open the article and confirm before you attribute words to anyone.
