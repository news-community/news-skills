#!/usr/bin/env python3
"""
alaska_desk.py, a READ-ONLY research client for the alaskanews.com public API.

For external Alaska creators (community journalists, bloggers, civic writers) to
pull published articles, meeting transcripts, public events, and prior-coverage
RAG into their OWN work. It never writes back to the platform: submitting content
back to the newsroom is a separate, editor-authenticated workflow, not this tool.

Terms of use are the site's own, declared at alaskanews.com/llms.txt:
`ai-train=no, search=yes, ai-input=yes` -> you may quote WITH attribution and a
backlink; you may not train models on the content. Every mode's output carries
that reminder, because the person running this is republishing someone else's
reporting.

## HATEOAS: every output points onward

The API and this client both follow a HATEOAS discipline: every response tells you
where to go next, so no external map is needed.

- CONSUMING the server's: API responses carry a `next_steps` array
  (`{rel, method, href, description}`). Non-JSON output surfaces them; `--json`
  passes them through in the payload for machine consumers.
- EMITTING our own: every mode ends with prioritized Next steps (with the WHY),
  the related modes, and a See also. No dead ends. Errors carry recovery paths.

## Auth: your own key, and only what it reaches

Each user supplies their OWN `cn_` key (env `ALASKA_DESK_API_KEY`, or a `.env.local`
next to this script). `digest` needs none; `search`/`angles`/`article`/`transcript`
/`events`/`rag`/`communities` need a valid key. Browsing the clip library is NOT a
role you can be granted: `GET /clips` authenticates by cookie session only and
rejects every API key, admin included. `check` reports what YOUR key can reach,
and names the endpoints no key reaches.

## Discovery: the five Ws (angles mode)

`angles` scaffolds the five-Ws investigative method for a READ-ONLY consumer. That
method has two modes: MATCHING (rank related coverage) is the server's job and stays
there; DISCOVERY (fix two Ws, expand the rest) is a human workflow of chained
searches, which a thin client CAN scaffold. `angles` fixes two Ws (an intent) and
runs the one framed search that intent implies, then hands back the nested-expansion
plan as next-steps, so the journalist drives depth, not the key's rate limit. See
SKILL.md's "Working the story" section.

Auth + HTTP + env plumbing is inlined below; stdlib only, no dependencies.

    ALASKA_DESK_API_KEY=cn_...  python3 alaska_desk.py search "port of alaska settlement"
    python3 alaska_desk.py digest            # no key needed
    python3 alaska_desk.py check             # what can my key reach?
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE = "https://alaskanews.com"
LICENSE_NOTE = (
    "Source: alaskanews.com. Per its llms.txt: ai-train=no, search=yes, ai-input=yes. "
    "Quote with attribution and a backlink; do not train on it."
)
UA = "alaska-desk/1.0"
RELATED_MODES = ("digest · browse · search · angles · article · transcript · events · people · "
                 "person · topics · tags · rag · clip · communities · check")
SEE_ALSO = "SKILL.md  ·  full API: alaskanews.com/docs/api"


# --- auth + HTTP + env plumbing (inlined; stdlib only, no dependencies) -------

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_API_BASE = "https://alaskanews.com/api/v1"
DEFAULT_COMMUNITY = "alaska-news"
# Pseudo-statuses for failures that are not HTTP statuses. Negative so they can
# never collide with a real code.
NON_JSON = -1   # transport worked, payload was not JSON
TIMED_OUT = -2  # API is up, it just did not answer in time
# /rag/query synthesizes an answer over retrieved passages and is far slower than
# every other mode: measured 84s on 2026-09-09, against the 60s default that used
# to cut it off and report "unreachable".
RAG_TIMEOUT = 180


class ApiError(Exception):
    def __init__(self, code, body=""):
        self.code = code
        self.body = body
        super().__init__(f"HTTP {code}: {body[:300]}")


def _load_env():
    """Read KEY=VALUE lines from .env / .env.local next to this script OR in the
    current directory, without overriding anything already set in the environment.
    Checking both means the key file is found whether you run from the script's
    folder or from your project root."""
    seen = set()
    for d in (SCRIPT_DIR, Path.cwd()):
        for name in (".env", ".env.local"):
            p = (d / name).resolve()
            if p in seen or not p.exists():
                continue
            seen.add(p)
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_api_key():
    _load_env()
    key = os.environ.get("ALASKA_DESK_API_KEY")
    if not key:
        print("Error: ALASKA_DESK_API_KEY not set.", file=sys.stderr)
        print("Create a key at alaskanews.com/profile/settings, then set it:", file=sys.stderr)
        print("  export ALASKA_DESK_API_KEY=cn_...", file=sys.stderr)
        print("  # or: echo 'ALASKA_DESK_API_KEY=cn_...' >> .env.local  (next to this script)", file=sys.stderr)
        sys.exit(2)
    return key


def api_request(method, path, params=None, body=None, timeout=60):
    base = os.environ.get("PLATFORM_API_BASE", DEFAULT_API_BASE)
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Accept": "application/json",
        "User-Agent": UA,
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode("utf-8", "replace"))
    except (TimeoutError, socket.timeout):
        # NOT the same as unreachable, and saying "unreachable" sends the reader
        # to check their network when the API is up and merely slow. /rag/query
        # synthesizes an answer and measured 84s on 2026-09-09.
        raise ApiError(TIMED_OUT, f"{path} did not answer within {timeout}s")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise ApiError(TIMED_OUT, f"{path} did not answer within {timeout}s")
        raise ApiError(0, f"unreachable: {e.reason}")
    # Not every 200 on this API is JSON: /clips/<id>/stream 302s to an MP4 in
    # storage, and a proxy or captive portal can return HTML. Decoding those as
    # JSON used to raise UnicodeDecodeError/JSONDecodeError straight through
    # ApiError's net and print a traceback. Fail like every other error here:
    # a status, a why, and a recovery.
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError(NON_JSON, f"{path} returned {len(raw)} bytes that are not JSON")


def api_redirect(path, timeout=30):
    """Resolve a redirecting endpoint to its target WITHOUT following it.

    `/clips/<id>/stream` 302s to a public MP4. Following that gets you video
    bytes, which is not something a research client can render; the useful
    answer is the URL itself, which the caller can hand to a player or curl."""
    base = os.environ.get("PLATFORM_API_BASE", DEFAULT_API_BASE)
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {get_api_key()}", "User-Agent": UA})
    try:
        with opener.open(req, timeout=timeout) as r:
            # No redirect: the endpoint answered directly (an error body, say).
            return {"status": r.status, "location": None,
                    "body": r.read(4096).decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            loc = e.headers.get("Location")
            # Location may legally be relative; a caller needs something it can
            # actually fetch, so resolve it against the request URL.
            return {"status": e.code,
                    "location": urllib.parse.urljoin(url, loc) if loc else None,
                    "body": ""}
        raise ApiError(e.code, e.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        raise ApiError(0, f"unreachable: {e.reason}")


# The eight corpora /search queries. Verified against the live API 2026-09-09;
# `search --corpus <name>` with a name outside this set returns nothing.
# external_documents and social_post are editor/admin only: naming one explicitly
# is a 403, omitting --corpus drops them silently and returns the rest.
CORPORA = ("articles", "users", "tags", "transcripts", "speakers", "events",
           "external_documents", "social_post")
RESTRICTED_CORPORA = frozenset({"external_documents", "social_post"})


def _check_corpora(spec):
    """Reject a corpus name the API does not have, and warn before asking for one
    it gates.

    A typo used to travel all the way to the server and come back as an empty
    result set, which reads exactly like "no coverage exists" and is the single
    most misleading answer a research tool can give a reporter."""
    asked = [c.strip() for c in spec.split(",") if c.strip()]
    unknown = [c for c in asked if c not in CORPORA]
    if unknown:
        sys.exit(
            f"Unknown corpus: {', '.join(unknown)}.\n"
            f"  Valid: {', '.join(CORPORA)}\n"
            "  Why this matters: an unknown name returns an empty result set, which looks\n"
            "  identical to 'nothing has been published about this'."
        )
    gated = [c for c in asked if c in RESTRICTED_CORPORA]
    if gated:
        print(f"Note: {', '.join(gated)} is editor/admin only and will 403 for a consumer key. "
              "Omit --corpus to have it dropped silently instead.", file=sys.stderr)


def _add_paging(p, default_limit):
    """Every list endpoint answers {data, count, offset, limit, has_more}. Without
    --offset a caller can only ever see the first page, and has_more becomes a
    fact the tool states but cannot act on."""
    p.add_argument("--limit", type=int, default=default_limit)
    p.add_argument("--offset", type=int, default=0, help="skip this many (paging)")


def _add_date_range(p):
    """The When axis. /search grew date_from/date_to on 2026-08-14, which is the
    only one of the five Ws the server can filter on, and the axis `angles`
    intents talk about holding or expanding. Shared so search and angles cannot
    drift apart on it."""
    p.add_argument("--since", metavar="YYYY-MM-DD", help="only results on/after this date (When axis)")
    p.add_argument("--until", metavar="YYYY-MM-DD", help="only results on/before this date (When axis)")


def _date_params(args):
    """Map --since/--until onto the API's date_from/date_to, omitting unset ones."""
    out = {}
    if getattr(args, "since", None):
        out["date_from"] = args.since
    if getattr(args, "until", None):
        out["date_to"] = args.until
    return out


# The two-axis grid from the five-Ws investigative method, as a sourcing scaffold.
# Each intent FIXES two Ws and names (fixed axes prose, expand prose, corpora to
# pull). One framed /search call, not a fan-out: the nesting is handed back as
# next-steps so the journalist drives depth.
INTENTS = {
    #            fixed axes                    expand (context)   corpora
    "similar":   ("What + Why",               "When + Where",     "articles"),
    "precedent": ("What + Why (ignore When)",  "When",            "articles,transcripts"),
    "track":     ("Who + What",               "When",            "articles,transcripts"),
    "local":     ("Where + What",             "Who",             "articles,events,transcripts"),
    "angle":     ("Why + What",               "Who",             "articles"),
}


# --- HATEOAS -----------------------------------------------------------------

def _server_next_steps(resp) -> list:
    """The API's OWN next_steps, wherever it put them (top level or under data).
    The API uses `next_steps: [{rel, method, href, description}]`."""
    if not isinstance(resp, dict):
        return []
    ns = resp.get("next_steps")
    if not ns and isinstance(resp.get("data"), dict):
        ns = resp["data"].get("next_steps")
    out = []
    for s in (ns or []):
        if isinstance(s, dict):
            rel = s.get("rel") or s.get("action") or ""
            method = s.get("method") or "GET"
            href = s.get("href") or ""
            desc = s.get("description") or ""
            out.append(f"{method} {href}  ({rel}){(' - ' + desc) if desc else ''}".strip())
        else:
            out.append(str(s))
    return out


def _skill_next_steps(mode, args, has_key) -> list:
    """State-driven next actions for THIS skill: (action, why). Priority order,
    capped at 5 by the caller. State shows up as `has_key` and per-mode context."""
    if mode == "digest":
        steps = []
        if not has_key:
            steps.append(("echo 'ALASKA_DESK_API_KEY=cn_...' >> .env.local ; then `check`",
                          "digest is the only keyless mode; a key unlocks search, angles, transcripts, and rag"))
        steps += [
            ('search "<topic from a headline above>"',
             "internal before external: confirm what Alaska News already has before you write"),
            ('angles "<topic>" --intent track',
             "work it as a story: fix Who+What, expand the rest (the five Ws)"),
        ]
        return steps
    if mode == "check":
        if not has_key:
            return [("set ALASKA_DESK_API_KEY, then re-run `check`",
                     "only `digest` works without a key; the rest report their reach once a key is set")]
        return [('search "<topic>"', "your key reached the search surface; start there"),
                ('angles "<topic>" --intent similar', "or work a story across the five Ws"),
                ("digest", "or browse recent stories first to find a topic")]
    if mode == "search":
        return [
            ("article <id from a result above>", "open a match's full body to quote (hold What: this is your story)"),
            ('rag "<same topic>"', "expand What+Why across time, ignore When: prior coverage + precedent"),
            ('angles "<topic>" --intent similar', "widen into discovery: fix two Ws, expand the rest"),
            ('search "<topic>" --corpus transcripts', "shift to the public record (the When/Where axis)"),
        ]
    if mode == "article":
        return [
            ('rag "<this article\'s topic>"', "gather supporting quotes and prior coverage (What+Why, varying When)"),
            ('angles "<topic>" --intent track', "work the actor as a beat: fix Who+What, expand When"),
            ('search "<a related angle>"', "find sibling stories to cite as 'previously reported'"),
        ]
    if mode == "transcript":
        return [('search "<meeting topic>" --corpus articles', "find the article(s) that covered this meeting"),
                ("events", "the When axis: what other public meetings are upcoming"),
                ('angles "<meeting topic>" --intent local', "fix Where+What: the local landscape around it")]
    if mode == "events":
        return [('search "<an event\'s topic>" --corpus articles,transcripts',
                 "get the coverage and the record for a specific event"),
                ('angles "<topic>" --intent track', "fix Who+What on the convening body; expand When")]
    if mode == "rag":
        return [("article <id from a quote's source>", "open the article a quote came from"),
                ('angles "<topic>" --intent angle', "fix Why+What: who else deploys this framing"),
                ('search "<topic>"', "widen beyond the RAG hits")]
    if mode == "angles":
        # Discovery is nested: one intent fixes two Ws; the next steps expand a
        # free axis or pivot the fixed pair. Placeholders (not the live seed) match
        # the house style of the other modes and keep this args-free.
        return [
            ("article <id from a hit above>",
             "open a match, then confirm it agrees on a SECOND axis, not just the topic"),
            ('rag "<seed>"',
             "expand What+Why across time (ignore When): prior coverage and precedent"),
            ('angles "<seed>" --intent track   (or: local, precedent, angle)',
             "pivot the fixed pair: each intent fixes a different two Ws and expands the rest"),
        ]
    if mode == "people":
        return [("person <id from a row above>",
                 "open the actor: their record plus every article that quotes them"),
                ('angles "<their name>" --intent track',
                 "work them as a beat: fix Who+What, expand When"),
                ('search "<their name>" --corpus transcripts',
                 "hear them in the public record rather than in coverage")]
    if mode == "person":
        return [("article <id from the coverage above>",
                 "open a story the quote came from, to cite it rather than the excerpt"),
                ('angles "<their name>" --intent track',
                 "fix Who+What and expand When: the actor as a running beat"),
                ("browse --tag <a tag from their coverage>",
                 "widen from the person to the subject they keep appearing in")]
    if mode == "topics":
        return [("tags --category topic", "narrow from the beat to the specific subjects inside it"),
                ("browse --tag <slug>", "read what has actually been published on one"),
                ('search "<topic name>"', "or go straight to a query inside the beat")]
    if mode == "tags":
        return [("browse --tag <slug from above>", "that tag's coverage, newest first"),
                ("topics", "or step up to the broad beat this subject sits in"),
                ('angles "<tag name>" --intent local', "fix Where+What around it")]
    if mode == "browse":
        return [("article <id from a row above>", "open one in full"),
                ('search "<something you noticed>"',
                 "switch from what EXISTS to what MATCHES, once you have a lead"),
                ("browse --sort top --window week",
                 "or re-cut the same list by what readers actually read")]
    if mode == "communities":
        return [('search "<topic>" --community <slug from above>',
                 "point the read surface at a specific community"),
                ("digest", "or stay on the default community's recent stories")]
    if mode == "clip":
        return [("transcript <source-id>", "read the full transcript the clip was cut from"),
                ("curl -o clip.mp4 '<the url above>'", "the id resolves to a public MP4; nothing here downloads it")]
    return []


def _print_hateoas(mode, args, resp=None):
    """The CLI HATEOAS footer: surface the server's next_steps, then this skill's,
    then related modes + see-also. Never called in --json mode (machine consumers
    read next_steps from the payload)."""
    has_key = bool(os.environ.get("ALASKA_DESK_API_KEY"))
    server = _server_next_steps(resp)
    if server:
        print("\nThe API points onward to:")
        for s in server[:5]:
            print(f"  {s}")
    steps = _skill_next_steps(mode, args, has_key)
    if steps:
        print("\nNext steps:")
        for action, why in steps[:5]:
            print(f"  {action}")
            print(f"      {why}")
    print(f"\nRelated modes: {RELATED_MODES}")
    print(f"See also: {SEE_ALSO}")


# --- helpers ----------------------------------------------------------------

def fetch_markdown(url: str, timeout: int = 30) -> str:
    """Public markdown surface (no key): the homepage digest and per-article body."""
    req = urllib.request.Request(url, headers={"Accept": "text/markdown", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        raise ApiError(0, f"unreachable: {e.reason}")


def _guided(fn):
    """Run an api_request-using command and translate auth failures into recovery
    a consumer can act on (HATEOAS error discipline), not a raw HTTP body."""
    try:
        return fn()
    except ApiError as e:
        if e.code == 401:
            key = os.environ.get("ALASKA_DESK_API_KEY", "")
            if key and not key.startswith("cn_"):
                sys.exit(
                    f"Not authorized (401). Your key starts with {key[:4]!r}, but alaskanews API "
                    "keys start with 'cn_' (cn_ + 40 hex).\n"
                    "  That looks like a key for a different service. Recovery: create an alaskanews "
                    "key at alaskanews.com/profile/settings and put it in a .env.local next to this script."
                )
            sys.exit(
                "Not authorized (401). This mode needs your alaskanews API key (starts with 'cn_').\n"
                "  Recovery: echo 'ALASKA_DESK_API_KEY=cn_...' >> .env.local\n"
                "  Then: python3 alaska_desk.py check\n"
                "  Get a key at alaskanews.com/profile/settings."
            )
        if e.code == 403:
            sys.exit(
                "Forbidden (403). Your key is valid but its role does not permit this.\n"
                "  Why: the external_documents and social_post search corpora are editor/admin "
                "only. Asking for them by name is a 403; leaving --corpus off drops them silently "
                "and returns the rest.\n"
                "  Recovery: run `check` to see your reach, and stay on "
                "articles/transcripts/events/tags/speakers/users, which any valid key reaches."
            )
        if e.code == TIMED_OUT:
            sys.exit(
                f"Timed out ({e.body}).\n"
                "  Why: the API is reachable but slow for this query; `rag` synthesizes an\n"
                "  answer over retrieved passages and routinely takes over a minute.\n"
                "  Recovery: narrow the query, or re-run: nothing was written, so a retry is safe."
            )
        if e.code == NON_JSON:
            sys.exit(
                f"Unexpected non-JSON response ({e.body}).\n"
                "  Why: usually a proxy or captive portal answering instead of the API.\n"
                "  Recovery: confirm you can reach alaskanews.com, then re-run `check`."
            )
        if e.code == 429:
            sys.exit("Rate limited (429). Recovery: back off ~a minute; the API allows 300 reads/min per user.")
        raise


def _emit(obj, args, render=None, mode=""):
    """Single output point for keyed modes. JSON: valid JSON only (its own
    next_steps are the HATEOAS for machines). Markdown: rendered data + the CLI
    HATEOAS footer + the license reminder."""
    if args.json:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
        return
    print(render(obj) if render else json.dumps(obj, indent=2, ensure_ascii=False))
    if mode:
        _print_hateoas(mode, args, obj)
    print(f"\n---\n{LICENSE_NOTE}")


# --- modes ------------------------------------------------------------------

def cmd_digest(args):
    """Recent-stories markdown homepage. Public, no key. The on-ramp."""
    md = fetch_markdown(SITE + "/")
    if args.json:
        print(json.dumps({"markdown": md}, ensure_ascii=False))
        return
    print(md.rstrip())
    _print_hateoas("digest", args, None)
    print(f"\n---\n{LICENSE_NOTE}")


def cmd_article(args):
    """Full article. A URL or slug uses the public markdown surface (no key); a
    bare id uses GET /articles/<id> (keyed, richer: sources, persons)."""
    ref = args.ref
    looks_like_path = ref.startswith("http") or "/" in ref
    if looks_like_path:
        url = ref if ref.startswith("http") else f"{SITE}/c/{DEFAULT_COMMUNITY}/{ref}"
        if args.json:
            print(json.dumps({"markdown": fetch_markdown(url)}, ensure_ascii=False))
            return
        print(fetch_markdown(url).rstrip())
        _print_hateoas("article", args, None)
        print(f"\n---\n{LICENSE_NOTE}")
    else:
        resp = _guided(lambda: api_request("GET", f"/articles/{ref}"))

        def render(r):
            a = r.get("data") if isinstance(r, dict) else None
            if not isinstance(a, dict) or "title" not in a:
                return json.dumps(r, indent=2, ensure_ascii=False)
            head = [f"# {a.get('title')}"]
            meta = "  ".join(x for x in (
                (a.get("published_at") or "")[:10],
                a.get("location") or "",
                f"{a.get('word_count')} words" if a.get("word_count") else "",
                f"~{a.get('estimated_read_minutes')} min" if a.get("estimated_read_minutes") else "",
            ) if x)
            if meta:
                head.append(meta)
            if a.get("slug"):
                head.append(f"{SITE}/c/{args.community}/{a['slug']}")
            for label in ("tldr", "excerpt"):
                if a.get(label):
                    head += ["", f"## {label}", str(a[label]).strip()]
            body = a.get("content") or a.get("body") or ""
            if body:
                head += ["", "## body", str(body).strip()]
            else:
                head += ["", "(no body in this payload: fetch by slug or URL for the full markdown, "
                             "or use --json to see every field)"]
            return "\n".join(head)

        _emit(resp, args, render, mode="article")


def _result_line(corpus, it):
    """One rendered search-result line, shared by `search` and `angles` so the
    display-field logic (tuned against live shapes) can't drift between them.

    Display field varies by corpus (verified live 2026-07-23): articles=title,
    tags/speakers=name/display_name, events=event_title, transcripts=source_title,
    social=body_text, docs=title/summary. Actionable id: a transcript's is its
    source_id (feed `transcript`); everything else uses id, falling back to slug."""
    title = (it.get("title") or it.get("name") or it.get("display_name")
             or it.get("event_title") or it.get("source_title")
             or it.get("summary") or it.get("body_text") or it.get("content")
             or "(untitled)")
    rid = it.get("source_id") if corpus == "transcripts" else (it.get("id") or it.get("slug") or "")
    when = (it.get("published_at") or it.get("event_date") or "")[:10]
    return (f"- {str(title).strip()[:140]}"
            + (f"  ({when})" if when else "")
            + (f"  [{rid}]" if rid else ""))


def _render_corpora(data, limit):
    """Render a /search `data` dict (corpus -> {results,total}) as grouped lines,
    or a shape-mismatch note. Shared by `search` and `angles`."""
    if not isinstance(data, dict):
        return ["(unexpected response shape; use --json to inspect)"]
    out = []
    for corpus, block in data.items():
        results = (block or {}).get("results") or []
        out.append(f"\n## {corpus} ({(block or {}).get('total', len(results))})")
        for it in results[:limit]:
            out.append(_result_line(corpus, it))
    return out


def cmd_search(args):
    """Unified multi-corpus search. `community` is required by the API."""
    params = {"q": args.query, "community": args.community, "limit": args.limit}
    params.update(_date_params(args))
    if args.corpus:
        _check_corpora(args.corpus)
        params["corpus"] = args.corpus
    resp = _guided(lambda: api_request("GET", "/search", params))

    def render(r):
        out = [f"# search: {args.query!r}  (corpus: {args.corpus or 'all'})"]
        out += _render_corpora(r.get("data") if isinstance(r, dict) else None, args.limit)
        return "\n".join(out)

    _emit(resp, args, render, mode="search")


def cmd_angles(args):
    """Discovery mode (the five-Ws investigative method): fix two Ws (an intent),
    pull the corpora that intent implies in ONE framed /search, and frame the hits
    as fixed-vs-expanding axes. Read-only: it only GETs /search. It does one level;
    the nesting is handed back as Next steps, so the journalist drives depth, not
    the key's rate limit."""
    fixed, expand, corpora = INTENTS[args.intent]
    params = {"q": args.seed, "community": args.community, "corpus": corpora, "limit": args.limit}
    params.update(_date_params(args))
    resp = _guided(lambda: api_request("GET", "/search", params))

    def render(r):
        out = [
            f"# angles: {args.seed!r}",
            f"Intent: {args.intent}  (fix {fixed}; expand {expand})",
            "Held on the fixed axes; the hits below vary the rest. One level only: nest via Next steps.",
        ]
        out += _render_corpora(r.get("data") if isinstance(r, dict) else None, args.limit)
        out.append("\nCorroboration: trust a match only when a SECOND axis agrees. A hit that shares "
                   "only the topic is one-axis (an anecdote), not corroboration.")
        return "\n".join(out)

    _emit(resp, args, render, mode="angles")


def _mmss(t):
    try:
        s = int(float(t))
        return f"{s // 60:02d}:{s % 60:02d}"
    except (TypeError, ValueError):
        return "--:--"


def cmd_transcript(args):
    """A meeting transcript's text chunks (speaker + timestamps). Keyed.

    Live-verified shape (2026-07-23): a top-level dict with `chunks`
    (chunk_index, content, speaker, start_time, end_time), `speakerMap`, `total`,
    `status`. Falls back to raw JSON if the shape ever changes."""
    resp = _guided(lambda: api_request("GET", f"/transcript/{args.source_id}/chunks", {"limit": args.limit}))

    def render(r):
        chunks = r.get("chunks") if isinstance(r, dict) else None
        if not isinstance(chunks, list):
            return json.dumps(r, indent=2, ensure_ascii=False)
        out = [f"# transcript {args.source_id}  ({r.get('status', '?')}, {r.get('total', len(chunks))} chunks)"]
        for c in chunks[: args.limit]:
            out.append(f"[{_mmss(c.get('start_time'))}] {c.get('speaker') or '?'}: "
                       f"{str(c.get('content', '')).strip()}")
        return "\n".join(out)

    _emit(resp, args, render, mode="transcript")


def cmd_events(args):
    """Genuinely UPCOMING public events, from GET /calendar.

    This used to run `/search?corpus=events`, which ranks by relevance and not by
    date. On 2026-09-09 that returned 15 of 15 events already in the past under a
    heading that said "upcoming", which is the one thing a hearing listing must
    never do: the whole use is deciding what you can still attend or still file
    comment on. `/calendar` is the date-ranged endpoint (start defaults to now,
    end to now+30d) and is what "upcoming" actually means.

    `/calendar` has no full-text parameter, so a query filters the window
    client-side on title and location. To search events by relevance across all
    time (including past ones), use `search <q> --corpus events`."""
    now = _dt.datetime.now(_dt.timezone.utc)
    params = {
        "community": args.community,
        "start": now.isoformat(),
        "end": (now + _dt.timedelta(days=args.days)).isoformat(),
        "limit": min(200, max(args.limit, 50) if args.query else args.limit),
    }
    if args.type:
        params["types"] = args.type
    resp = _guided(lambda: api_request("GET", "/calendar", params))

    def render(r):
        events = ((r.get("data") or {}).get("events")) if isinstance(r, dict) else None
        if not isinstance(events, list):
            return json.dumps(r, indent=2, ensure_ascii=False)
        if args.query:
            q = args.query.lower()
            events = [e for e in events
                      if q in f"{e.get('event_title') or ''} {e.get('event_location') or ''}".lower()]
        head = f"# events: next {args.days} days"
        if args.query:
            head += f", matching {args.query!r}"
        out = [head]
        if not events:
            out.append(f"(nothing in the window{' matching that' if args.query else ''}. "
                       f"Widen with --days, or use `search` to reach past events.)")
        for e in events[: args.limit]:
            when = (e.get("event_date") or "")[:16].replace("T", " ")
            where = e.get("event_location") or ""
            kind = e.get("event_type") or ""
            out.append(f"- {e.get('event_title') or '(untitled)'}")
            meta = "  ".join(x for x in (when, where, f"({kind})" if kind else "") if x)
            out[-1] += (f"\n    {meta}" if meta else "") + (f"  [{e.get('id')}]" if e.get("id") else "")
        return "\n".join(out)

    _emit(resp, args, render, mode="events")


def cmd_rag(args):
    """Prior-coverage RAG: a synthesized answer plus the citations behind it.

    Live-verified shape (2026-09-09): `data` carries `answer` (markdown, with
    [F4]/[H2]-style refs), `citations` ({ref, kind, verbatim_excerpt, speaker,
    url, source_id}), `pools`, `retrieval` and `token_usage`. The citations are
    the point: an answer you cannot trace is not usable in reporting, and the
    excerpt + url are what let you quote a source rather than a summary of it."""
    resp = _guided(lambda: api_request(
        "POST", "/rag/query",
        body={"query": args.query, "community": args.community}, timeout=RAG_TIMEOUT))

    def render(r):
        d = r.get("data") if isinstance(r, dict) else None
        if not isinstance(d, dict) or "answer" not in d:
            return json.dumps(r, indent=2, ensure_ascii=False)
        out = [f"# rag: {args.query!r}  ({d.get('mode', '?')})", "", str(d.get("answer", "")).strip()]
        cites = d.get("citations") or []
        if cites:
            out += ["", f"## citations ({len(cites)})"]
            for c in cites[: args.limit]:
                who = f", {c['speaker']}" if c.get("speaker") else ""
                out.append(f"- [{c.get('ref', '?')}] {c.get('kind', '')}{who}")
                if c.get("verbatim_excerpt"):
                    out.append(f'    "{str(c["verbatim_excerpt"]).strip()[:220]}"')
                if c.get("url"):
                    out.append(f"    {c['url']}")
            if len(cites) > args.limit:
                out.append(f"  (+{len(cites) - args.limit} more; --limit to widen, --json for all)")
        out.append("\nQuote the CITATION, not the answer: the synthesized text is a summary of "
                   "someone else's reporting, and the excerpt + url are what you can attribute.")
        return "\n".join(out)

    _emit(resp, args, render, mode="rag")


def cmd_clip(args):
    """Resolve a KNOWN clip id to its MP4 URL.

    `/clips/<id>/stream` 302s to a public storage object, so there is no JSON to
    render: the answer IS the URL. It is returned unfollowed, so nothing here
    downloads video. Browsing the clip library (`GET /clips`) is a separate
    endpoint that takes cookie-session auth ONLY and rejects every API key, so
    ids come from `search` or an article, not from this tool."""
    r = _guided(lambda: api_redirect(f"/clips/{args.clip_id}/stream"))
    url = r.get("location")
    if args.json:
        print(json.dumps({"clip_id": args.clip_id, "stream_url": url,
                          "status": r.get("status")}, indent=2))
        return
    if url:
        print(f"# clip {args.clip_id}\n{url}")
    else:
        print(f"# clip {args.clip_id}\nNo redirect (HTTP {r.get('status')}). "
              f"{r.get('body', '')[:300]}")
    _print_hateoas("clip", args, None)
    print(f"\n---\n{LICENSE_NOTE}")


def cmd_communities(args):
    """List the community slugs `--community` accepts.

    Every keyed mode requires a community and the API rejects an unknown slug,
    but nothing in this client used to tell you what the valid ones ARE, so the
    only discoverable value was the default baked into the source."""
    resp = _guided(lambda: api_request("GET", "/communities", {"limit": 100}))

    def render(r):
        rows = r.get("data") if isinstance(r, dict) else None
        if not isinstance(rows, list):
            return json.dumps(r, indent=2, ensure_ascii=False)
        out = [f"# communities ({len(rows)})"]
        for c in rows:
            if not isinstance(c, dict):
                continue
            mark = "  <- default" if c.get("slug") == DEFAULT_COMMUNITY else ""
            out.append(f"- {c.get('slug', '?'):24} {c.get('name', '')}{mark}")
        out.append("\nPass one as --community <slug>.")
        return "\n".join(out)

    _emit(resp, args, render, mode="communities")


def _paged(resp):
    """The list envelope's pagination line, or "" when it isn't a list response.

    List endpoints answer {data, count, offset, limit, has_more, total?}. A page
    that silently drops the rest is how a reporter concludes "there are only
    three" when there are ninety, so has_more is rendered, not swallowed."""
    if not isinstance(resp, dict) or "has_more" not in resp:
        return ""
    shown = resp.get("count", 0)
    start = resp.get("offset", 0)
    total = resp.get("total")
    line = f"showing {start + 1}-{start + shown}" + (f" of {total}" if total is not None else "")
    if resp.get("has_more"):
        line += f"  (more: --offset {start + (resp.get('limit') or shown)})"
    return line


def _article_lines(rows, limit):
    """One rendered line per article, shared by every mode that lists articles so
    the date and id cannot go missing from one of them."""
    out = []
    for a in (rows or [])[:limit]:
        if not isinstance(a, dict):
            continue
        when = (a.get("published_at") or "")[:10]
        out.append(f"- {str(a.get('title') or '(untitled)').strip()[:130]}"
                   + (f"  ({when})" if when else "")
                   + (f"  [{a.get('id') or a.get('slug') or ''}]"
                      if (a.get("id") or a.get("slug")) else ""))
        # persons/<id>/articles carries the actual quote that tied the person to
        # the story. That excerpt IS the Who axis; a bare title is just a link.
        if a.get("verbatim_excerpt"):
            n = a.get("attribution_count") or 0
            out.append(f'    quoted{f" ({n}x)" if n else ""}: '
                       f'"{str(a["verbatim_excerpt"]).strip()[:200]}"')
    return out


def cmd_people(args):
    """The Who axis as a directory: named speakers, filterable by substring and
    role. `angles --intent track` fixes Who+What but had no way to LOOK UP a
    who, so the actor had to be spelled exactly right from memory."""
    params = {"community": args.community, "limit": args.limit, "offset": args.offset}
    if args.query:
        params["q"] = args.query
    if args.role:
        params["role"] = args.role
    resp = _guided(lambda: api_request("GET", "/persons", params))

    def render(r):
        rows = r.get("data") if isinstance(r, dict) else None
        if not isinstance(rows, list):
            return json.dumps(r, indent=2, ensure_ascii=False)
        out = [f"# people{': ' + repr(args.query) if args.query else ''}"]
        if not rows:
            out.append("(no match. Names are as published: try a surname alone.)")
        for p in rows:
            desc = "  ".join(x for x in (p.get("title") or "", p.get("organization") or "",
                                         p.get("district") or "") if x)
            out.append(f"- {p.get('display_name') or '(unnamed)'}"
                       + (f"  ({p.get('role')})" if p.get("role") else "")
                       + f"  [{p.get('id', '')}]")
            if desc:
                out.append(f"    {desc}")
        page = _paged(r)
        if page:
            out.append(f"\n{page}")
        return "\n".join(out)

    _emit(resp, args, render, mode="people")


def cmd_person(args):
    """One person, plus the published articles they appear in.

    Two calls, both GET: the record and their coverage. It is the one place this
    client makes more than one request per run, because a person without their
    coverage is a contact card, and the coverage without the person is a list of
    links whose relevance you have to take on trust.

    "Appears in", not "quoted in", and the difference is load-bearing. The
    endpoint returns a UNION of two things: articles where an attribution matched
    this person's NAME, and articles structurally linked to them. Only the first
    kind carries a verbatim excerpt, so a row without one is an association the
    platform asserts rather than a quote you can attribute. Rows are marked
    accordingly, because "Dunleavy appears in this piece" and "Dunleavy said this
    in this piece" are different claims and only one of them is quotable."""
    who = _guided(lambda: api_request("GET", f"/persons/{args.person_id}"))
    cov = _guided(lambda: api_request(
        "GET", f"/persons/{args.person_id}/articles",
        {"limit": args.limit, "offset": args.offset}))
    if args.json:
        print(json.dumps({"person": who, "articles": cov}, indent=2, ensure_ascii=False))
        return
    # GET /persons/<id> nests the record under data.speaker (alongside data.aliases),
    # unlike the list endpoint which returns person objects directly.
    d = (who.get("data") if isinstance(who, dict) else None) or {}
    p = d.get("speaker") if isinstance(d.get("speaker"), dict) else d
    out = [f"# {p.get('display_name') or args.person_id}"]
    meta = "  ".join(x for x in (p.get("role") or "", p.get("title") or "",
                                 p.get("organization") or "", p.get("district") or "",
                                 p.get("location") or "") if x)
    if meta:
        out.append(meta)
    aliases = [a.get("alias") or a.get("name") for a in (d.get("aliases") or [])
               if isinstance(a, dict)]
    if aliases:
        out.append("also known as: " + ", ".join(str(a) for a in aliases if a))
    for field in ("bio", "website"):
        if p.get(field):
            out.append(f"{field}: {str(p[field]).strip()[:400]}")
    rows = cov.get("data") if isinstance(cov, dict) else None
    out.append(f"\n## appears in ({(cov or {}).get('total', len(rows or []))})")
    out += _article_lines(rows, args.limit) or ["(no linked coverage)"]
    if rows and not any((r or {}).get("verbatim_excerpt") for r in rows if isinstance(r, dict)):
        out.append("\n(No row here carries a verbatim excerpt, so these are structural links "
                   "rather than matched quotes. Open one and confirm before writing that this "
                   "person said anything in it.)")
    page = _paged(cov)
    if page:
        out.append(f"\n{page}")
    print("\n".join(out))
    _print_hateoas("person", args, cov)
    print(f"\n---\n{LICENSE_NOTE}")


def cmd_topics(args):
    """The ~15 broad desks (Health, Education, Government), with how much has
    been published under each. Distinct from `tags`: a topic is the BEAT, a tag
    is the subject inside it. Both exist server-side and they are not the same
    vocabulary, which is why this client exposes both rather than picking one."""
    resp = _guided(lambda: api_request("GET", "/topics", {"limit": args.limit, "offset": args.offset}))

    def render(r):
        rows = r.get("data") if isinstance(r, dict) else None
        if not isinstance(rows, list):
            return json.dumps(r, indent=2, ensure_ascii=False)
        # The endpoint returns article_count / source_count / total_views, and on
        # 2026-09-09 every one of the 15 topics reported 0 for all three. Printing
        # "0 articles" against a beat that HAS coverage is the same failure as an
        # empty result set: it reads as "nothing published here". So the counts
        # are shown only where the platform actually populates them, and their
        # absence is stated once rather than rendered fifteen times as a zero.
        any_counts = any(t.get("article_count") for t in rows if isinstance(t, dict))
        out = [f"# topics ({len(rows)})"]
        for t in rows:
            n = t.get("article_count")
            counts = f"{n} articles" if (any_counts and n) else ""
            out.append(f"- {str(t.get('name', '?'))[:28]:28} {counts}  [{t.get('slug', '')}]")
        if not any_counts:
            out.append("\n(The API reports 0 articles for every topic: these stats are not being "
                       "populated, so read them as UNKNOWN, not as an empty beat. Use "
                       "`browse --tag <slug>` for what a subject actually has.)")
        out.append("\nA topic is the beat; `tags` is the subject vocabulary inside it.")
        page = _paged(r)
        if page:
            out.append(page)
        return "\n".join(out)

    _emit(resp, args, render, mode="topics")


def cmd_tags(args):
    """The subject vocabulary: organizations, topics and locations that coverage
    is filed under. `--category` narrows; the slug is what `browse --tag` takes."""
    params = {"limit": args.limit, "offset": args.offset}
    if args.query:
        params["q"] = args.query
    if args.category:
        params["category"] = args.category
    resp = _guided(lambda: api_request("GET", "/tags", params))

    def render(r):
        rows = r.get("data") if isinstance(r, dict) else None
        if not isinstance(rows, list):
            return json.dumps(r, indent=2, ensure_ascii=False)
        out = [f"# tags{': ' + repr(args.query) if args.query else ''}"
               + (f"  (category: {args.category})" if args.category else "")]
        if not rows:
            out.append("(no match)")
        for t in rows:
            out.append(f"- {str(t.get('name', '?'))[:44]:44} {t.get('category', ''):13} "
                       f"[{t.get('slug', '')}]")
            if t.get("description"):
                out.append(f"    {str(t['description']).strip()[:110]}")
        page = _paged(r)
        if page:
            out.append(f"\n{page}")
        out.append("\nOpen a tag's coverage with: browse --tag <slug>")
        return "\n".join(out)

    _emit(resp, args, render, mode="tags")


# Sort modes the article list accepts. Verified against the live API 2026-09-09.
SORTS = ("hot", "new", "timeline", "top", "popular", "alphabetical")
TIME_WINDOWS = ("today", "week", "month", "all")


def cmd_browse(args):
    """The published article list, without a search query.

    `search` answers "what do you have about X". This answers "what has been
    published", which is a different question and the one you ask before you know
    what X is. With `--tag <slug>` it lists a single beat's coverage instead.

    GET /feed is deliberately NOT wrapped: it returns byte-identical results to
    `/articles?sort=new` (checked 2026-09-09) and accepts no community parameter,
    so for a consumer targeting a community it is the same mode with less reach."""
    if args.tag:
        path, params = f"/tags/{args.tag}/articles", {"limit": args.limit, "offset": args.offset}
    else:
        path = "/articles"
        params = {"community": args.community, "limit": args.limit,
                  "offset": args.offset, "sort": args.sort}
        if args.sort == "top" and args.window:
            params["t"] = args.window
    resp = _guided(lambda: api_request("GET", path, params))

    def render(r):
        rows = r.get("data") if isinstance(r, dict) else None
        if not isinstance(rows, list):
            return json.dumps(r, indent=2, ensure_ascii=False)
        head = f"# browse: tag {args.tag}" if args.tag else f"# browse: {args.sort}"
        out = [head] + (_article_lines(rows, args.limit) or ["(nothing published here)"])
        page = _paged(r)
        if page:
            out.append(f"\n{page}")
        return "\n".join(out)

    _emit(resp, args, render, mode="browse")


# (label, method, path, params, body) for the keyed probes. digest is separate.
# `clips` and `transcripts/search` are deliberately absent: both authenticate via
# cookie session only (platform reads `supabase.auth.getUser()` rather than going
# through runApiHandler), so they 401 for EVERY API key including an admin's.
# Probing them taught the reader a role they could acquire, which was false.
KEYED_PROBES = [
    ("articles", "GET", "/articles", {"limit": 1, "community": "alaska-news"}, None),
    ("search", "GET", "/search", {"q": "alaska", "community": "alaska-news", "limit": 1}, None),
    ("transcripts", "GET", "/transcripts", {"limit": 1}, None),
    ("calendar (events)", "GET", "/calendar", {"community": "alaska-news", "limit": 1}, None),
    ("communities", "GET", "/communities", {"limit": 1}, None),
    ("rag", "POST", "/rag/query", None, {"query": "test", "community": "alaska-news"}),
]
# Endpoints an API key can never reach, whatever its role. Reported so `check`
# answers the question "why can't I browse clips?" once, instead of leaving the
# reader to seek a role upgrade that cannot help.
KEY_BLIND_ENDPOINTS = [
    ("clips (browse)", "cookie-session auth only; no API key reaches it"),
    ("transcripts/search", "cookie-session auth only; use `search --corpus transcripts`"),
]
_STATUS = {401: "needs a key", 403: "forbidden (role/scope)", 429: "rate-limited",
           0: "unreachable", TIMED_OUT: "timed out (slow, not blocked)",
           NON_JSON: "non-JSON reply"}


def cmd_check(args):
    """Report what THIS key can actually reach, so a user learns their access
    before building on it. Mirrors the auth spike, and stays quiet when no key is
    set rather than erroring once per endpoint."""
    _load_env()
    print("alaska-desk reachability:\n")

    try:
        fetch_markdown(SITE + "/", timeout=15)
        print(f"  {'digest (public)':26} OK")
    except ApiError as e:
        print(f"  {'digest (public)':26} {_STATUS.get(e.code, f'HTTP {e.code}')}")

    key = os.environ.get("ALASKA_DESK_API_KEY")
    if not key:
        print(f"  {'(keyed modes)':26} no key set")
    else:
        if not key.startswith("cn_"):
            print(f"  {'(key format)':26} WRONG: starts {key[:4]!r}, alaskanews keys start 'cn_'")
        key_ok = key.startswith("cn_")
        for label, method, path, params, body in KEYED_PROBES:
            try:
                # rag is the slow one; give it its real budget so a healthy key
                # is not reported as unreachable by a probe that gave up early.
                api_request(method, path, params=params, body=body,
                            timeout=RAG_TIMEOUT if path == "/rag/query" else 30)
                status = "OK"
            except ApiError as e:
                if e.code == 401:
                    # A valid cn_ key that 401s on ONE endpoint while others pass is
                    # a role gate, not a bad key. Only call it a bad key if the
                    # prefix is wrong.
                    status = "no access (role)" if key_ok else "rejected (bad key)"
                else:
                    status = _STATUS.get(e.code, f"HTTP {e.code}")
            print(f"  {label:26} {status}")

    print("\n  Not reachable by ANY api key (not a role you can be granted):")
    for label, why in KEY_BLIND_ENDPOINTS:
        print(f"  {label:26} {why}")

    _print_hateoas("check", args, None)
    print(f"\n---\n{LICENSE_NOTE}")


def main():
    _load_env()  # so has_key is knowable in every footer, digest/check included

    # Shared flags live on a parent parser added to every subcommand, so they work
    # AFTER the mode (`digest --json`), which is the order a CLI user reaches for.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true",
                        help="Raw JSON (its next_steps are the machine HATEOAS)")
    common.add_argument("--community", default=DEFAULT_COMMUNITY,
                        help=f"Community slug (default {DEFAULT_COMMUNITY})")

    ap = argparse.ArgumentParser(
        description="Read-only research client for the alaskanews.com public API (external consumers).",
        epilog=f"Every mode ends with Next steps (HATEOAS). Related modes: {RELATED_MODES}.")
    sub = ap.add_subparsers(dest="mode", required=True)

    sub.add_parser("digest", parents=[common], help="Recent stories (public, no key)")
    sub.add_parser("check", parents=[common], help="What can my key reach?")
    sub.add_parser("communities", parents=[common],
                   help="List community slugs valid for --community")

    p = sub.add_parser("search", parents=[common], help="Multi-corpus semantic + keyword search")
    p.add_argument("query")
    p.add_argument("--corpus", help=f"comma-sep, default all: {','.join(CORPORA)} "
                                    "(external_documents and social_post are editor/admin only)")
    _add_date_range(p)
    p.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("angles", parents=[common],
                       help="Discovery: fix two Ws (an intent), expand the rest (the five Ws)")
    p.add_argument("seed", help="the story seed (a topic, or an entity for --intent track)")
    p.add_argument("--intent", choices=list(INTENTS), default="similar",
                   help="which two Ws to fix (default: similar = What+Why)")
    _add_date_range(p)
    p.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("people", parents=[common], help="Who-axis directory: named speakers")
    p.add_argument("query", nargs="?", default="", help="substring match on the name")
    p.add_argument("--role", help="filter by role, e.g. official, candidate")
    _add_paging(p, 20)

    p = sub.add_parser("person", parents=[common],
                       help="One person, plus every article quoting them (with the quote)")
    p.add_argument("person_id", help="person id (from `people`)")
    _add_paging(p, 10)

    p = sub.add_parser("topics", parents=[common], help="The broad beats, with article counts")
    _add_paging(p, 30)

    p = sub.add_parser("tags", parents=[common], help="Subject vocabulary: orgs, topics, locations")
    p.add_argument("query", nargs="?", default="", help="substring match on name/slug/aliases")
    p.add_argument("--category", choices=("organization", "topic", "location"))
    _add_paging(p, 20)

    p = sub.add_parser("browse", parents=[common],
                       help="Published articles without a query (what IS there, not what matches)")
    p.add_argument("--sort", choices=SORTS, default="new")
    p.add_argument("--window", choices=TIME_WINDOWS, help="only with --sort top")
    p.add_argument("--tag", help="list one tag's coverage instead (slug from `tags`)")
    _add_paging(p, 10)

    p = sub.add_parser("article", parents=[common], help="Full article by URL/slug (public) or id (keyed)")
    p.add_argument("ref", help="article id, slug, or full URL")

    p = sub.add_parser("transcript", parents=[common], help="Meeting transcript chunks by source id")
    p.add_argument("source_id")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("events", parents=[common],
                       help="Upcoming public meetings/hearings (date-ranged, via /calendar)")
    p.add_argument("query", nargs="?", default="", help="optional substring filter on title/location")
    p.add_argument("--days", type=int, default=30, help="size of the forward window (default 30)")
    p.add_argument("--type", help="event type, e.g. meeting, public_notice, community_event, class")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("rag", parents=[common],
                       help="Prior-coverage RAG: synthesized answer + citations (slow: ~1-2 min)")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=8, help="citations to render (default 8)")

    p = sub.add_parser("clip", parents=[common], help="Stream a KNOWN clip id (browse needs editor role)")
    p.add_argument("clip_id")

    args = ap.parse_args()
    {
        "digest": cmd_digest, "check": cmd_check, "search": cmd_search, "angles": cmd_angles,
        "article": cmd_article, "transcript": cmd_transcript, "events": cmd_events,
        "rag": cmd_rag, "clip": cmd_clip, "communities": cmd_communities,
        "people": cmd_people, "person": cmd_person, "topics": cmd_topics,
        "tags": cmd_tags, "browse": cmd_browse,
    }[args.mode](args)


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        print(f"API error: {e}\n  Recovery: run `check` to confirm your key's reach, or --json to inspect.",
              file=sys.stderr)
        sys.exit(1)
