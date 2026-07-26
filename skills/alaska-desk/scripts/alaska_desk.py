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
/`events`/`rag` need a valid key; `clip` browse needs an editor role most external
keys lack. `check` reports what YOUR key can reach.

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
import json
import os
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
RELATED_MODES = "digest · search · angles · article · transcript · events · rag · clip · check"
SEE_ALSO = "SKILL.md  ·  full API: alaskanews.com/docs/api"


# --- auth + HTTP + env plumbing (inlined; stdlib only, no dependencies) -------

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_API_BASE = "https://alaskanews.com/api/v1"
DEFAULT_COMMUNITY = "alaska-news"


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
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        raise ApiError(0, f"unreachable: {e.reason}")


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
    if mode == "clip":
        return [("transcript <source-id>", "read the full transcript the clip was cut from")]
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
                "Forbidden (403). Your key is valid but its scope/role does not permit this.\n"
                "  Why: browsing clips and the external-documents / social-post search corpora "
                "need an editor role most external keys lack.\n"
                "  Recovery: run `check` to see your reach, and stay on articles/transcripts/search, "
                "which any valid key reaches."
            )
        if e.code == 429:
            sys.exit("Rate limited (429). Recovery: back off ~a minute; the API allows ~100 GET/min per key.")
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
        _emit(resp, args, mode="article")


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
    return f"- {str(title).strip()[:140]}" + (f"  [{rid}]" if rid else "")


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
    if args.corpus:
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
    """Upcoming public events (hearings, assemblies, meetings), via the events
    search corpus. GET /events itself is POST-only on the platform, so search is
    the read path. Live-verified: results carry event_title/date/location/type."""
    params = {"q": args.query or "meeting hearing assembly", "community": args.community,
              "corpus": "events", "limit": args.limit}
    resp = _guided(lambda: api_request("GET", "/search", params))

    def render(r):
        results = (((r.get("data") or {}).get("events") or {}).get("results")) if isinstance(r, dict) else None
        if not isinstance(results, list):
            return json.dumps(r, indent=2, ensure_ascii=False)
        out = [f"# events: {args.query or '(upcoming)'}"]
        for e in results[: args.limit]:
            when = e.get("event_date") or ""
            where = e.get("event_location") or ""
            kind = e.get("event_type") or ""
            line = f"- {e.get('event_title') or '(untitled)'}"
            meta = "  ".join(x for x in (when, where, f"({kind})" if kind else "") if x)
            out.append(line + (f"\n    {meta}" if meta else "") + (f"  [{e.get('id')}]" if e.get("id") else ""))
        return "\n".join(out)

    _emit(resp, args, render, mode="events")


def cmd_rag(args):
    """Prior-coverage RAG: quote pool, people facts, history, general facts."""
    resp = _guided(lambda: api_request("POST", "/rag/query", body={"query": args.query, "community": args.community}))
    _emit(resp, args, mode="rag")


def cmd_clip(args):
    """Stream metadata for a KNOWN clip id. Browsing the clip library needs an
    editor role; this only reaches a clip you already have an id for (public
    stream). Discover ids via `search` or a transcript."""
    resp = _guided(lambda: api_request("GET", f"/clips/{args.clip_id}/stream"))
    _emit(resp, args, mode="clip")


# (label, method, path, params, body) for the keyed probes. digest is separate.
KEYED_PROBES = [
    ("articles", "GET", "/articles", {"limit": 1, "community": "alaska-news"}, None),
    ("search", "GET", "/search", {"q": "alaska", "community": "alaska-news", "limit": 1}, None),
    ("transcripts", "GET", "/transcripts", {"limit": 1}, None),
    ("clips (browse)", "GET", "/clips", {"community": "alaska-news", "limit": 1}, None),
    ("rag", "POST", "/rag/query", None, {"query": "test", "community": "alaska-news"}),
]
_STATUS = {401: "needs a key", 403: "forbidden (role/scope)", 429: "rate-limited", 0: "unreachable"}


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
                api_request(method, path, params=params, body=body)
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

    p = sub.add_parser("search", parents=[common], help="Multi-corpus semantic + keyword search")
    p.add_argument("query")
    p.add_argument("--corpus", help="comma-sep: articles,transcripts,events,speakers,tags (default: all)")
    p.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("angles", parents=[common],
                       help="Discovery: fix two Ws (an intent), expand the rest (the five Ws)")
    p.add_argument("seed", help="the story seed (a topic, or an entity for --intent track)")
    p.add_argument("--intent", choices=list(INTENTS), default="similar",
                   help="which two Ws to fix (default: similar = What+Why)")
    p.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("article", parents=[common], help="Full article by URL/slug (public) or id (keyed)")
    p.add_argument("ref", help="article id, slug, or full URL")

    p = sub.add_parser("transcript", parents=[common], help="Meeting transcript chunks by source id")
    p.add_argument("source_id")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("events", parents=[common], help="Upcoming public meetings/hearings")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("rag", parents=[common], help="Prior-coverage RAG (quotes, people, history)")
    p.add_argument("query")

    p = sub.add_parser("clip", parents=[common], help="Stream a KNOWN clip id (browse needs editor role)")
    p.add_argument("clip_id")

    args = ap.parse_args()
    {
        "digest": cmd_digest, "check": cmd_check, "search": cmd_search, "angles": cmd_angles,
        "article": cmd_article, "transcript": cmd_transcript, "events": cmd_events,
        "rag": cmd_rag, "clip": cmd_clip,
    }[args.mode](args)


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        print(f"API error: {e}\n  Recovery: run `check` to confirm your key's reach, or --json to inspect.",
              file=sys.stderr)
        sys.exit(1)
