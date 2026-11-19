#!/usr/bin/env python3
"""
cite_check.py: check the quotes in a draft against a local newsroom's record, and write
the citations for the ones it finds.

For a community journalist, blogger or civic writer with a draft that quotes public
officials or the newsroom's own reporting. For each quotation in the draft it searches
the newsroom's meeting transcripts and articles and reports one of:

  VERBATIM   the words appear exactly (ignoring case, punctuation and curly quotes)
  CLOSE      a passage nearly matches; the source's own wording is shown
  NOT FOUND  nothing matched in what was searched, which is NOT evidence the quote is
             wrong: the source may be outside this newsroom
  NOT SEARCHED  a part the key does not reach (transcripts need a subscriber's key)

For a transcript match it also says whether the speaker the transcript names matches
the person the draft attributes the quote to, and gives a link that opens the
transcript at that moment. Every match comes with a citation in the form the newsroom's
own usage terms ask for: attribution and a backlink.

READ-ONLY against the newsroom. What leaves your machine is each quotation's words, as a
search query, with your key; the draft itself is never sent. `--dry-run` lists exactly
what would be sent and sends nothing. On your own machine it writes one file, and only
when asked: `--out FILE` saves the report there, replacing a file already at that path.

Every newsroom request goes through local_news_api.py, the Local News API client
shipped beside this file as a byte-identical copy.

    python3 cite_check.py draft.md
    python3 cite_check.py draft.md --dry-run
    cat draft.md | python3 cite_check.py -
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import re
import shlex
import sys
import unicodedata
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_news_api as lna  # noqa: E402  (the shared client, shipped beside this file)

NAME = "cite-check"
VERSION = "0.2.2"
UA = f"{NAME}/{VERSION}"
lna.UA = UA  # the shared client reads this global on every request

# A passage counts as CLOSE when its words match the quote's at least this well
# (difflib's ratio over word sequences of the quote's length). CALIBRATE: a starting
# value chosen when this was written, not measured against real misquotes. It is a
# flag for a person to look at, never a verdict, so the cost of a wrong setting is a
# missed or a spurious "look at this", shown with both wordings side by side.
CLOSE_RATIO = 0.8
# Below this many words a quotation is usually a phrase ("so-called", a title, a
# name) rather than something someone said, and searching it is noise.
DEFAULT_MIN_WORDS = 5
# How many words of a long quotation go into the search query. The comparison
# itself always uses the whole quotation.
QUERY_WORDS = 24

SOURCE_START, SOURCE_END = lna.SOURCE_START, lna.SOURCE_END

VERBS = (r"said|says|told|tells|wrote|writes|added|adds|asked|asks|stated|states|explained|"
         r"testified|argued|noted|responded|replied|warned|according to")
# A name is up to four capitalised words, where a word carries no full stop unless it
# is an initial ("J."). Allowing a stop inside a word let "said Jane Doe. Also" read
# as the name "Jane Doe. Also" on the first live run.
_NAME_WORD = r"[A-Z](?:\.|[\w'\u2019-]+)"
# An abbreviated title before a name ("Sen. Lisa Murkowski"). Without it the name read
# as "Sen", which said nothing about who spoke, so the speaker check fell silent.
_TITLE = (r"(?:(?:Sen|Rep|Gov|Lt|Dr|Mr|Mrs|Ms|Mx|Sgt|Capt|Cpl|Det|Atty|Supt|Rev|Hon|Gen|Col|Maj|"
          r"Cmdr|Prof|Insp|Asst)\.\s+)?")
NAME_RE = r"(" + _TITLE + _NAME_WORD + r"(?:\s+(?:" + _NAME_WORD + r"|de|van|von|la|le)){0,3})"
# Words AP style puts right after an attribution ("said Jane Doe Wednesday"). They are
# capitalised, so the name pattern takes them, and then the surname read as the day.
_AFTER_NAME = frozenset("monday tuesday wednesday thursday friday saturday sunday "
                        "today tonight yesterday tomorrow".split())


def fence(text):
    """The client's own fence, not a copy: a copy here kept a one-pass escape after
    the client's was fixed, so `<<<<<END ...` still closed it from inside."""
    return lna._fence(text)


# --- finding the quotations in a draft ---------------------------------------------

_QUOTE_RES = (
    re.compile(r"“([^“”]+?)”"),        # curly double quotes
    # Straight double quotes, across a line wrap but not a blank line: a stray `"`
    # must not pair with one a paragraph later, and a quotation wrapped in a
    # Markdown draft used to be skipped without being counted.
    re.compile(r"(?<![\w])\"((?:[^\"\n]|\n(?![^\S\n]*\n))+?)\"(?![\w])"),
)


def _attribution(before, after):
    """The person the draft attributes a quotation to, read from the words around it.
    A heuristic, reported as "the draft attributes it to", never as a fact."""
    def clean(name):
        # A name ending a sentence carries its full stop ("said Jane Doe."), which
        # would then fail every comparison with a transcript's speaker label.
        words = name.rstrip(".,;:").split()
        while len(words) > 1 and words[-1].lower() in _AFTER_NAME:
            words.pop()
        return " ".join(words)
    m = re.match(r"\s*,?\s*(?:" + VERBS + r")\s+" + NAME_RE, after)
    if m:
        return clean(m.group(1))
    m = re.match(r"\s*,?\s*" + NAME_RE + r"\s+(?:" + VERBS + r")\b", after)
    if m and m.group(1).split()[0] not in ("He", "She", "They", "It", "We", "I"):
        return clean(m.group(1))
    m = re.search(NAME_RE + r"\s+(?:" + VERBS + r")\s*[,:]?\s*$", before)
    if m:
        return clean(m.group(1))
    return None


def find_quotes(text, min_words=DEFAULT_MIN_WORDS):
    """Quotations in the draft, in order, without duplicates: dicts with the quote,
    its attribution (or None) and the line it starts on."""
    # One line ending everywhere: a draft piped through stdin keeps CRLF, and a
    # paragraph break written as \r\n\r\n then read as no break at all.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    seen, out = set(), []
    spans = []
    for rx in _QUOTE_RES:
        for m in rx.finditer(text):
            spans.append((m.start(), m.end(), m.group(1)))
    for start, end, q in sorted(spans):
        q = " ".join(q.split())
        if len(re.findall(r"\w+", q)) < min_words:
            continue
        key = normalize(q)
        if key in seen:
            continue
        seen.add(key)
        out.append({"quote": q,
                    "attributed_to": _attribution(text[max(0, start - 120):start], text[end:end + 120]),
                    "line": text.count("\n", 0, start) + 1})
    return out


# --- comparing words ----------------------------------------------------------------

_FOLD = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                       "\u2013": "-", "\u2014": "-", "\u00a0": " "})


def words_of(text):
    """Lowercased words with their spans in the original text."""
    text = unicodedata.normalize("NFKC", str(text)).translate(_FOLD)
    return [(m.group(0).lower(), m.start(), m.end()) for m in re.finditer(r"[\w']+", text)], text


def normalize(text):
    return " ".join(w for w, _, _ in words_of(text)[0])


def plain_text(markdown):
    """An article's Markdown as the words a reader sees. A link's URL is not part of
    the sentence it sits in, and left in it breaks every quotation that runs across
    a linked phrase, which in this newsroom's articles is most of them."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", markdown)          # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)            # [words](url) -> words
    text = re.sub(r"https?://\S+", " ", text)                       # bare URLs
    return re.sub(r"[*_`>#]+", " ", text)                           # emphasis and headings


def compare(quote, source_text):
    """('verbatim' | 'close' | None, the source's own wording or None, ratio)."""
    q = [w for w, _, _ in words_of(quote)[0]]
    src, folded = words_of(source_text)
    if not q or not src:
        return None, None, 0.0
    sw = [w for w, _, _ in src]
    n = len(q)
    # Exact: the quote's words appear in order, contiguously.
    for i in range(0, len(sw) - n + 1):
        if sw[i:i + n] == q:
            return "verbatim", folded[src[i][1]:src[i + n - 1][2]], 1.0
    # Close: the best window of the quote's length, by word-sequence similarity.
    qset = set(q)
    best = (0.0, None)
    for i in range(0, max(1, len(sw) - n + 1)):
        window = sw[i:i + n]
        if len(qset.intersection(window)) < max(1, n // 2):
            continue
        r = difflib.SequenceMatcher(None, q, window, autojunk=False).ratio()
        if r > best[0]:
            best = (r, i)
    if best[1] is not None and best[0] >= CLOSE_RATIO:
        i = best[1]
        j = min(i + n, len(src)) - 1
        return "close", folded[src[i][1]:src[j][2]], round(best[0], 3)
    return None, None, round(best[0], 3)


# Words in a name or a speaker label that say what someone is, not who: sharing
# one ("Mayor", "Member") says nothing about whether two names are one person.
_NOT_NAMES = frozenset(
    "mr mrs ms mx dr hon honorable sen senator rep representative gov governor lt mayor deputy "
    "vice assembly assemblymember member council councilmember councilor councilwoman councilman "
    "chair chairman chairwoman chairperson president commissioner superintendent director judge "
    "justice chief officer sgt sergeant capt captain lieutenant manager clerk attorney secretary "
    "trustee board school city borough state the of jr sr ii iii iv cpl det atty supt rev gen col "
    "maj cmdr prof insp asst phd md esq jd cpa dds rn".split())
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'", "\u02bb": "'"})


def _name_words(name):
    """The words of a name, lowercased, with accents and apostrophe styles folded, so
    "Jos\u00e9 N\u00fa\u00f1ez" and "Jose Nunez", or O'Malley in either apostrophe, compare equal.
    Titles and suffixes are dropped; initials are kept as one letter."""
    text = unicodedata.normalize("NFKD", str(name).translate(_APOSTROPHES))
    text = "".join(c for c in text if not unicodedata.combining(c))
    words = [w.strip("'-").lower() for w in re.findall(r"[^\W\d_](?:[^\W\d_]|['-])*", text)]
    return [w for w in words if w and w not in _NOT_NAMES]


def _surnames(word):
    """A surname and, for a hyphenated one, each of its parts: "Smith-Jones" is
    labelled "Smith" or "Jones" often enough."""
    return {word, *[p for p in word.split("-") if len(p) > 1]}


def same_person(draft_name, speaker):
    """Whether a draft's attribution and a transcript's speaker label can be the same
    person, judged on the surname. True when the surnames agree; False when they
    differ (both full names, or a lone name that is not in the other); None when
    nothing can be said: a side missing, a placeholder label ("Speaker 2"), only a
    title, or a lone first name that the other shares. Any shared word used to
    count, so "John Smith" matched "John Jones" and "Mayor A" matched "Mayor B",
    and the speaker warning never showed."""
    if not draft_name or not speaker or re.match(r"(?i)^(speaker|unknown|unidentified)\b", speaker):
        return None
    full_a, full_b = _name_words(draft_name), _name_words(speaker)
    # The surname is the last word that is more than an initial.
    a = [w for w in full_a if len(w) > 1]
    b = [w for w in full_b if len(w) > 1]
    if not a or not b:
        return None
    if not _surnames(a[-1]) & _surnames(b[-1]):
        if len(a) == 1 or len(b) == 1:
            lone, full = (a, b) if len(a) == 1 else (b, a)
            return None if any(_surnames(lone[0]) & _surnames(w) for w in full) else False
        return False
    # Same surname. Two different first names are two people ("John Smith" and
    # "Jane Smith"); an initial or a short form ("Rob", "Robert") is not evidence.
    if len(full_a) > 1 and len(full_b) > 1:
        fa, fb = full_a[0], full_b[0]
        if not (fa.startswith(fb) or fb.startswith(fa)):
            return False
    return True


# --- citations ------------------------------------------------------------------------

def article_url(site, community, art):
    """The article's page, or None when its slug or community is not shaped like a
    slug: the URL is fetched and printed, and both parts are the newsroom's text."""
    slug = lna._safe(art.get("slug"), slug=True)
    comm = lna._safe((art.get("communities") or {}).get("slug") or art.get("community_slug")
                     or community, slug=True)
    return f"{site}/c/{comm}/{slug}" if slug and comm else None


def transcript_url(site, chunk):
    t = chunk.get("start_time")
    tail = f"?t={int(float(t))}" if t is not None else ""
    return f"{site}/transcript/{urllib.parse.quote(str(chunk.get('source_id') or ''), safe='')}{tail}"


def newsroom_name(site):
    return re.sub(r"^https?://", "", site)


def cite_article(site, community, art):
    when = str(art.get("published_at") or "")[:10]
    title = str(art.get("title") or "(untitled)").strip()
    return f"\"{title},\" {newsroom_name(site)}" + (f", {when}" if when else "") + \
        f". {article_url(site, community, art)}"


def cite_transcript(site, chunk):
    who = chunk.get("speaker") or "unidentified speaker"
    return (f"{who}, {chunk.get('source_title') or 'a public meeting'}, at {lna._mmss(chunk.get('start_time'))}"
            f" (transcript via {newsroom_name(site)}). {transcript_url(site, chunk)}")


# --- checking ----------------------------------------------------------------------------

class Stop(Exception):
    """The run cannot usefully continue (rate limit, timeout): report what was done.
    `str()` is this tool's own summary; `detail` is what the server said, which is
    rendered fenced, never inline."""

    def __init__(self, summary, detail=None):
        super().__init__(summary)
        self.detail = detail


def search(quote, community, limit):
    words = re.findall(r"[\w']+", quote)
    params = {"q": " ".join(words[:QUERY_WORDS]), "community": community, "limit": limit,
              "corpus": "articles,transcripts"}
    try:
        resp = lna.api_request("GET", "/search", params)
    except lna.ApiError as e:
        if e.code in (401, 403, lna.CROSS_ORIGIN, lna.NON_JSON):
            lna._guided(lambda: _reraise(e))  # the client's recovery message, then exit
            raise
        if e.code == 429:
            raise Stop("rate limited (429); wait a minute and run it again")
        if e.code == lna.TIMED_OUT:
            raise Stop("a search timed out; run it again")
        if e.code == 0:
            raise Stop(f"could not reach {lna.site_host()}", detail=e.body)
        raise Stop(f"a search failed (HTTP {e.code})", detail=e.body)
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        raise Stop("the search answered in a shape this client does not know")
    return data, lna._refused(resp)


def _reraise(e):
    raise e


def check_quote(q, site, community, limit, articles_to_read, page_cache):
    """One quotation's finding, as data."""
    data, refused = search(q["quote"], community, limit)
    result = {**q, "status": "not found", "matches": [], "searched": [], "not_searched": {}}

    for corpus in ("transcripts", "articles"):
        if corpus in refused:
            result["not_searched"][corpus] = refused[corpus]
        elif not isinstance(data.get(corpus), dict):
            result["not_searched"][corpus] = "the server returned nothing for this part and gave no reason"
        else:
            result["searched"].append(corpus)

    if "transcripts" in result["searched"]:
        for chunk in data["transcripts"].get("results") or []:
            kind, wording, ratio = compare(q["quote"], chunk.get("content") or "")
            if kind:
                result["matches"].append({
                    "kind": kind, "source": "transcript", "ratio": ratio, "source_wording": wording,
                    "speaker": chunk.get("speaker"), "meeting": chunk.get("source_title"),
                    "at": lna._mmss(chunk.get("start_time")),
                    "speaker_matches_draft": same_person(q.get("attributed_to"), chunk.get("speaker")),
                    "url": transcript_url(site, chunk), "citation": cite_transcript(site, chunk)})

    read = 0
    if "articles" in result["searched"]:
        for art in (data["articles"].get("results") or [])[:articles_to_read]:
            url = article_url(site, community, art)
            if not url:
                continue
            if url not in page_cache:
                try:
                    page_cache[url] = plain_text(lna.fetch_markdown(url))
                except lna.ApiError as e:
                    page_cache[url] = None
                    result.setdefault("unread", []).append(f"{url} ({e.code or 'unreachable'})")
            body = page_cache[url]
            if body is None:
                continue
            read += 1
            kind, wording, ratio = compare(q["quote"], body)
            if kind:
                result["matches"].append({
                    "kind": kind, "source": "article", "ratio": ratio, "source_wording": wording,
                    "title": art.get("title"), "published": str(art.get("published_at") or "")[:10],
                    "url": url, "citation": cite_article(site, community, art)})
    result["articles_read"] = read

    order = {("verbatim", "transcript"): 0, ("verbatim", "article"): 1,
             ("close", "transcript"): 2, ("close", "article"): 3}
    result["matches"].sort(key=lambda m: (order[(m["kind"], m["source"])], -m["ratio"]))
    if result["matches"]:
        result["status"] = result["matches"][0]["kind"]
    elif not result["searched"]:
        result["status"] = "not searched"
    return result


# --- rendering -----------------------------------------------------------------------------

STATUS_LABEL = {"verbatim": "VERBATIM", "close": "CLOSE", "not found": "NOT FOUND",
                "not searched": "NOT SEARCHED"}


# A match is attribution, never verification: it says who said the words, or where they
# were published, and nothing about whether what they say is so.
NOT_A_TRUTH_CLAIM = ("A match shows who said these words, or where they were published, not that what "
                     "they say is true: a claim inside a quotation needs its own source.")


def _verbatim_advice(r):
    m = r["matches"][0]
    if m["source"] == "transcript":
        if m["speaker_matches_draft"] is False:
            # The label itself stays in the fenced source below: it is the
            # newsroom's text, and printed here it could speak from outside the fence.
            return ("The words are in the transcript, but under a different speaker from the one the "
                    "draft names (the label is in the source below). Speaker labels come from the "
                    "newsroom's processing and can be wrong: check the recording at the link before "
                    "you attribute these words.")
        return "On the public record. Cite the meeting and link the transcript at that moment."
    return ("These are the newsroom's published words. If they are its reporting rather than a quote "
            "it carried, attribute them to the newsroom and link the article.")


def _advice(r):
    if r["status"] == "verbatim":
        return f"{_verbatim_advice(r)} {NOT_A_TRUTH_CLAIM}"
    if r["status"] == "close":
        return ("A source says nearly this. Use the source's own words below, or paraphrase without "
                "quotation marks.")
    if r["status"] == "not searched":
        return "Nothing could be searched for this quotation with your key (see below)."
    return ("Nothing in what was searched matches. That is not evidence the quote is wrong: it may "
            "come from a source this newsroom does not hold. Find the primary record before you publish it.")


def render(report):
    site = report["newsroom"]
    out = [f"# Quote check: {report['draft']}",
           f"> {newsroom_name(site)}, community `{report['community']}`. {len(report['results'])} "
           f"quotation(s) of {report['min_words']}+ words checked. Generated {report['generated_utc']} UTC."]
    counts = {}
    for r in report["results"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    if counts:
        out.append("> " + ", ".join(f"{STATUS_LABEL[k]}: {v}" for k, v in counts.items()))
    if report.get("stopped"):
        out.append(f"> **Stopped early: {report['stopped']}.** "
                   f"{report['unchecked']} quotation(s) were not checked.")
        if report.get("stopped_detail"):
            # What the server answered, which is its text, not this tool's.
            out.append(fence(report["stopped_detail"]))

    for i, r in enumerate(report["results"], 1):
        out += ["", f"## {i}. {STATUS_LABEL[r['status']]} (line {r['line']})",
                f"> “{r['quote']}”"]
        if r.get("attributed_to"):
            out.append(f"The draft attributes it to: {r['attributed_to']}")
        out.append(_advice(r))
        if r["matches"]:
            m = r["matches"][0]
            src = [f"Where: {m.get('meeting') or m.get('title') or ''}"
                   + (f", {m['speaker']} at {m['at']}" if m["source"] == "transcript" else
                      (f", published {m['published']}" if m.get("published") else ""))]
            if m["kind"] == "close":
                src.append(f"The source's words ({int(m['ratio'] * 100)}% word match): “{m['source_wording']}”")
            src.append(f"Cite: {m['citation']}")
            out.append(fence("\n".join(src)))
            if len(r["matches"]) > 1:
                out.append(f"Also in {len(r['matches']) - 1} other place(s); `--json` lists them.")
        searched = ", ".join(r["searched"]) or "nothing"
        out.append(f"_Searched: {searched}"
                   + (f" ({r['articles_read']} article(s) read in full)" if "articles" in r["searched"] else "")
                   + "._")
        for corpus, why in r["not_searched"].items():
            extra = " Searching transcripts needs a subscriber's key." if corpus == "transcripts" else ""
            # The reason is usually the newsroom's own message, so it is fenced.
            out.append(f"_Not searched: {corpus}.{extra} The newsroom's reason:_")
            out.append(fence(why))
        for u in r.get("unread", []):
            out.append(f"_Could not read {u}._")

    cited = []
    for r in report["results"]:
        if r["matches"] and r["matches"][0]["citation"] not in cited:
            cited.append(r["matches"][0]["citation"])
    if cited:
        out += ["", "## Citations", "_Attribution and a backlink, as the newsroom's terms ask._"]
        out.append(fence("\n".join(f"- {c}" for c in cited)))
    return "\n".join(out)


# --- next steps (HATEOAS: every output says where to go next) ----------------------------------
# Each step is (command, reason, priority), highest first, at most five, pre-filled
# where the page holds the value. A value copied from the newsroom into a command
# must be shaped like an id or a slug (lna._safe): these commands sit outside the
# source-material fence and an agent may run them. The person's own input (the
# topic, the draft path) is shell-quoted instead. Timing is not carried: every step
# is something to do now.

REPO_URL = "https://github.com/news-community/news-skills"
CLIENT = "python3 scripts/local_news_api.py"


def _ranked(steps):
    """Highest priority first, at most five. Every builder includes a high step, so
    the first one is high on its own merits; nothing here relabels it."""
    order = ("high", "medium", "low")
    return sorted(steps, key=lambda s: order.index(s[2]))[:5]


def _cmd(text, why, prio):
    """A step that is a shell command, runnable as printed (a `<placeholder>` marks
    what you fill in)."""
    return (text, why, prio, True)


def _do(text, why, prio):
    """A step that is something to do, not a command."""
    return (text, why, prio, False)


def render_next(steps, related):
    out = ["", "## Next steps"]
    for i, (text, why, prio, is_cmd) in enumerate(steps, 1):
        out += [f"{i}. [{prio}] " + (f"`{text}`" if is_cmd else text), f"   {why}"]
    out += ["", "Related: " + " · ".join(related),
            f"See also: SKILL.md (in this skill's folder) · {REPO_URL}"]
    return "\n".join(out)


def _carry(args, spec):
    """The user's own non-default flags, shell-quoted, so a suggested rerun runs the
    same check on the same newsroom. spec: (dest, flag, default)."""
    out = []
    for dest, flag, default in spec:
        v = getattr(args, dest, default)
        if v is None or v == default:
            continue
        out.append(flag if v is True else f"{flag} {shlex.quote(str(v))}")
    return (" " + " ".join(out)) if out else ""


def json_next(steps):
    """--json keeps stdout the page itself, so the next steps go to stderr as JSON."""
    print(json.dumps({"next_steps": [
        {"command": t if is_cmd else None, "instruction": None if is_cmd else t, "reason": w, "priority": p}
        for t, w, p, is_cmd in steps]}, ensure_ascii=False), file=sys.stderr)


RELATED = ["local-news-api (the full client, shipped here as scripts/local_news_api.py; its `check` shows "
           "what your key reaches)",
           "meeting-prep (a public meeting's calendar entry, notice, coverage and what was said before)"]


DEFAULT_MAX_QUOTES = 25   # the CLI's existing default, named so the carry below cannot drift from it
# --max-quotes is carried so a check suggested after a dry run sends only the
# quotations the dry run showed; without it, the default of 25 came back.
CC_FLAGS = (("community", "--community", None), ("min_words", "--min-words", DEFAULT_MIN_WORDS),
            ("limit", "--limit", 5), ("read", "--read", 3), ("max_quotes", "--max-quotes", DEFAULT_MAX_QUOTES))


def _draft_token(draft_arg):
    """The draft as a shell word. A draft read from stdin cannot be re-read by a
    suggested command, so it becomes a placeholder for a saved file."""
    return "<your draft saved as a file>" if draft_arg == "-" else shlex.quote(draft_arg)


def next_steps(report, draft_arg, args=None):
    res, steps = report["results"], []
    draft = _draft_token(draft_arg)
    same = _carry(args, CC_FLAGS) if args is not None else ""
    mismatch = [r for r in res if r["matches"] and r["matches"][0].get("speaker_matches_draft") is False]
    if mismatch:
        steps.append(_do("open the transcript link under each speaker warning above",
                         f"{len(mismatch)} quotation(s) are on the record under a different speaker; attributing "
                         "them unchecked is the error a correction would have to fix", "high"))
    missing = [r for r in res if r["status"] == "not found"]
    if missing:
        words = " ".join(re.findall(r"[\w']+", missing[0]["quote"])[:8])
        steps.append(_cmd(f"{CLIENT} search {shlex.quote(words)} --corpus articles,transcripts,events",
                          f"{len(missing)} quotation(s) were not found; a looser search, or the primary record, "
                          "may hold them, and an unsourced quote should not run", "high"))
    if any("transcripts" in r["not_searched"] for r in res):
        steps.append(_cmd(f"{CLIENT} check",
                          "transcripts were not searched for your key (it needs a subscriber's); see what it "
                          "reaches", "medium"))
    if report.get("stopped") or report.get("skipped_by_max_quotes"):
        n = report.get("unchecked", 0) + report.get("skipped_by_max_quotes", 0)
        why = f"{n} quotation(s) were not checked"
        if "429" in str(report.get("stopped") or "") or "rate" in str(report.get("stopped") or "").lower():
            why += "; wait about a minute first, since the newsroom limited the rate, and this re-sends every one"
        others = _carry(args, tuple(f for f in CC_FLAGS if f[0] != "max_quotes")) if args is not None else ""
        steps.append(_cmd(f"python3 scripts/cite_check.py {draft} --max-quotes {len(res) + n}{others}", why,
                          "medium"))
    if res and all(r["status"] == "verbatim" for r in res):
        steps.append(_do("paste the Citations section into your draft",
                         "every quotation was found verbatim; attribution and a backlink are what the "
                         "newsroom's terms ask for", "high"))
    if not (args is not None and getattr(args, "out", None)):
        steps.append(_cmd(f"python3 scripts/cite_check.py {draft} --out citations.md{same}",
                          "keep this report beside the draft (this runs the searches again)", "low"))
    if not any(st[2] == "high" for st in steps):
        steps.append(_do("read each result above before you publish",
                         "nothing failed outright; the advice under each quotation says what to check", "high"))
    return _ranked(steps)


def dry_run_steps(draft_arg, n_quotes, args=None):
    draft = _draft_token(draft_arg)
    same = _carry(args, CC_FLAGS) if args is not None else ""
    steps = []
    if not n_quotes:
        lower = max(1, (getattr(args, "min_words", DEFAULT_MIN_WORDS) or DEFAULT_MIN_WORDS) - 2)
        rest = _carry(args, tuple(f for f in CC_FLAGS if f[0] != "min_words")) if args is not None else ""
        steps.append(_cmd(f"python3 scripts/cite_check.py {draft} --dry-run --min-words {lower}{rest}",
                          "no quotation was long enough to check; look for shorter ones", "high"))
        return _ranked(steps)
    if not lna.read_key():
        steps.append(_cmd(f"echo '{lna.KEY_ENV}=cn_<your key>' >> .env.local && "
                          f"python3 scripts/cite_check.py {draft}{same}",
                          "a check needs your own key; a dry run does not", "high"))
    else:
        steps.append(_cmd(f"python3 scripts/cite_check.py {draft}{same}",
                          "run the check: only the quoted words above are sent, never the draft", "high"))
    if (getattr(args, "min_words", DEFAULT_MIN_WORDS) if args is not None else DEFAULT_MIN_WORDS) > 3:
        rest = _carry(args, tuple(f for f in CC_FLAGS if f[0] != "min_words")) if args is not None else ""
        steps.append(_cmd(f"python3 scripts/cite_check.py {draft} --dry-run --min-words 3{rest}",
                          "include shorter quotations, if a short one matters to the story", "low"))
    return _ranked(steps)


def read_draft(path):
    if path == "-":
        return sys.stdin.read(), "stdin"
    p = Path(path)
    if not p.is_file():
        sys.exit(f"No such file: {path}")
    return p.read_text(encoding="utf-8", errors="replace"), p.name


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="cite_check.py",
        description="Check the quotations in a draft against a newsroom's transcripts and articles, and "
                    "write citations for the ones found. Sends each quotation's words, never the draft.")
    p.add_argument("draft", help="the draft file (Markdown or text), or - for stdin")
    p.add_argument("--community", help="newsroom community slug (default: NEWS_COMMUNITY or alaska-news)")
    p.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS,
                   help=f"skip quotations shorter than this (default {DEFAULT_MIN_WORDS})")
    p.add_argument("--max-quotes", type=int, default=DEFAULT_MAX_QUOTES,
                   help=f"check at most this many (default {DEFAULT_MAX_QUOTES})")
    p.add_argument("--limit", type=int, default=5, help="search results per part per quotation (default 5)")
    p.add_argument("--read", type=int, default=3,
                   help="articles read in full per quotation to compare wording (default 3)")
    p.add_argument("--dry-run", action="store_true",
                   help="list the quotations and exactly what would be sent; send nothing")
    p.add_argument("--json", action="store_true", help="print the report as JSON (terms go to stderr)")
    p.add_argument("--out", help="also save the report as Markdown at this path, replacing a file already there")
    args = p.parse_args(argv)
    if args.max_quotes < 1:
        p.error("--max-quotes must be at least 1")

    text, label = read_draft(args.draft)
    quotes = find_quotes(text, args.min_words)
    lna._load_env()
    site = lna.site()
    community = args.community or lna.default_community()

    if args.dry_run:
        shown = quotes[: args.max_quotes]
        sent = [" ".join(re.findall(r"[\w']+", q["quote"])[:QUERY_WORDS]) for q in shown]
        steps = dry_run_steps(args.draft, len(quotes), args)
        if args.json:
            print(json.dumps({"draft": label, "dry_run": True, "sent_to": f"{lna.api_base()}/search",
                              "quotations": [{"line": q["line"], "would_send": w, "attributed_to": q["attributed_to"]}
                                             for q, w in zip(shown, sent)],
                              "skipped_by_max_quotes": max(0, len(quotes) - args.max_quotes)},
                             indent=2, ensure_ascii=False))
            json_next(steps)
            return
        print(f"{len(quotes)} quotation(s) of {args.min_words}+ words in {label}. Nothing was sent.")
        print(f"Each would be sent to {lna.api_base()}/search as the query below, with your key; "
              "the draft itself is never sent.\n")
        for i, (q, w) in enumerate(zip(shown, sent), 1):
            who = f"  (attributed to {q['attributed_to']})" if q["attributed_to"] else ""
            print(f"{i}. line {q['line']}: {w}{who}")
        if len(quotes) > args.max_quotes:
            print(f"\n{len(quotes) - args.max_quotes} more would be skipped by --max-quotes.")
        print(render_next(steps, RELATED))
        return

    if not quotes:
        msg = (f"No quotations of {args.min_words}+ words found in {label}. Nothing was sent. "
               "Lower --min-words to check shorter ones.")
        if args.json:
            print(json.dumps({"draft": label, "results": [], "note": msg}, ensure_ascii=False))
        sys.exit(msg)
    lna.get_api_key()  # exits with the client's own guidance when no key is set

    print(f"Checking {min(len(quotes), args.max_quotes)} quotation(s) against {newsroom_name(site)}: "
          "each quotation's words go to its search with your key; the draft does not.", file=sys.stderr)
    results, cache, stopped, stopped_detail = [], {}, None, None
    todo = quotes[: args.max_quotes]
    for q in todo:
        try:
            results.append(check_quote(q, site, community, args.limit, args.read, cache))
        except Stop as s:
            stopped, stopped_detail = str(s), s.detail
            break
    report = {"draft": label, "newsroom": site, "community": community, "min_words": args.min_words,
              "results": results, "stopped": stopped, "stopped_detail": stopped_detail,
              "unchecked": len(todo) - len(results),
              "skipped_by_max_quotes": max(0, len(quotes) - args.max_quotes),
              "close_ratio": CLOSE_RATIO,
              "generated_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")}

    terms = lna.terms_note()
    steps = next_steps(report, args.draft, args)
    if args.json:
        report["terms"] = terms
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print(terms, file=sys.stderr)
        json_next(steps)
        return
    out = render(report)
    if report["skipped_by_max_quotes"]:
        out += f"\n\n_{report['skipped_by_max_quotes']} more quotation(s) not checked: raise --max-quotes._"
    out += "\n" + render_next(steps, RELATED)
    print(out)
    print(f"\n---\n{terms}")
    if args.out:
        Path(args.out).write_text(f"{out}\n\n---\n{terms}\n", encoding="utf-8")
        print(f"\n(Written to {args.out}.)")


if __name__ == "__main__":
    main()
