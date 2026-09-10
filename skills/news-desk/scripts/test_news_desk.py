#!/usr/bin/env python3
"""
Offline tests for news_desk.py.

The live API needs a per-user cn_ key, so the network path is unverified here (as
with any live-network path). Everything that does NOT touch the network is tested:
arg parsing, URL/param construction, the license reminder, and that keyed modes
fail with guidance rather than a traceback.

    python3 -m pytest test_news_desk.py -q
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_desk as ad  # noqa: E402

SCRIPT = str(Path(__file__).resolve().parent / "news_desk.py")


def run(*args, env=None):
    import os
    e = dict(os.environ)
    # Isolate from .env.local: popping is NOT enough, because the script's own
    # _load_env() re-reads the file and setdefault()s the key back in. Setting it
    # to "" blocks that (the key "exists" so setdefault won't override) and reads
    # as no-key. A test wanting a specific key overrides via env=.
    e["ALASKA_DESK_API_KEY"] = ""
    e["NEWS_DESK_API_KEY"] = ""
    # Terms are fetched from the configured site; keep tests on the default and
    # off any operator override that would change what they assert.
    e.pop("NEWS_SITE", None)
    e.pop("NEWS_COMMUNITY", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=e)


class TestLicenseDiscipline:
    def test_terms_are_read_from_the_newsroom_not_compiled_in(self, monkeypatch):
        """LICENSE_NOTE was a constant reciting one newsroom's stance. Pointed at
        a second newsroom it would have printed Alaska's terms over their work,
        which is the one staleness bug in this client with an ethical edge."""
        monkeypatch.setattr(ad, "_TERMS_CACHE", {})
        monkeypatch.setattr(ad, "content_signal",
                            lambda s, timeout=10: "ai-train=no, search=yes, ai-input=yes")
        note = ad.terms_note()
        for term in ("ai-train=no", "attribution", "backlink"):
            assert term in note
        assert not hasattr(ad, "LICENSE_NOTE"), "the constant should be gone, not shadowed"

    def test_digest_output_carries_attribution(self):
        # digest hits the public markdown surface; skip if offline
        r = run("digest")
        if r.returncode != 0 and "unreachable" in (r.stdout + r.stderr):
            pytest.skip("network unavailable")
        assert "ai-train=no" in r.stdout


class TestModeDispatch:
    def test_every_advertised_mode_parses(self):
        for mode, extra in [
            ("digest", []), ("check", []), ("search", ["q"]), ("angles", ["seed"]),
            ("article", ["some-slug"]), ("transcript", ["src-id"]), ("events", []),
            ("rag", ["q"]), ("clip", ["clip-id"]), ("communities", []),
            ("people", []), ("person", ["pid"]), ("topics", []), ("tags", []), ("browse", []),
        ]:
            # --help on a subparser exits 0 and proves the subcommand exists
            r = run(mode, "--help")
            assert r.returncode == 0, f"{mode} did not parse: {r.stderr}"

    def test_unknown_mode_is_rejected(self):
        assert run("frobnicate").returncode != 0

    def test_mode_is_required(self):
        assert run().returncode != 0


class TestGracefulAuth:
    def test_keyed_mode_without_key_guides_not_tracebacks(self):
        r = run("search", "port of alaska")
        assert r.returncode != 0
        blob = r.stdout + r.stderr
        assert "Traceback" not in blob
        assert "NEWS_DESK_API_KEY" in blob
        assert "cn_" in blob

    def test_check_without_key_is_quiet_and_clean(self):
        """check must not spew the missing-key error once per endpoint."""
        r = run("check")
        assert r.returncode == 0
        assert r.stdout.count("no key set") == 1
        assert "Error: ALASKA_DESK_API_KEY not set" not in r.stdout
        assert "digest (public)" in r.stdout

    def test_wrong_key_prefix_is_named_not_disguised_as_needs_a_key(self):
        """A live test (2026-07-23) hit a key with the wrong prefix (msk_ vs cn_)
        and the client said 'needs a key', which is misleading when a key IS set.
        check must call out the format, and a keyed mode must give the wrong-type
        recovery, not the no-key one."""
        r = run("check", env={"ALASKA_DESK_API_KEY": "msk_deadbeef"})
        if "unreachable" in (r.stdout + r.stderr):
            pytest.skip("network unavailable")
        assert "WRONG" in r.stdout and "cn_" in r.stdout
        assert "rejected" in r.stdout  # not "needs a key"

    def test_keyed_mode_with_wrong_prefix_gives_wrong_type_recovery(self):
        r = run("search", "test", env={"ALASKA_DESK_API_KEY": "msk_deadbeef"})
        if "unreachable" in (r.stdout + r.stderr):
            pytest.skip("network unavailable")
        blob = r.stdout + r.stderr
        assert "different service" in blob or "start with 'cn_'" in blob


class TestReadOnlyContract:
    def test_no_write_verbs_anywhere(self):
        """This is a CONSUMER skill. It must never PATCH/PUT/DELETE, and its only
        POST is the read-only /rag/query. A submit/write path creeping in would
        cross the line into an editorial/write capability this consumer tool must
        never have."""
        src = Path(SCRIPT).read_text()
        for verb in ('"PATCH"', '"PUT"', '"DELETE"'):
            assert verb not in src, f"write verb {verb} present in a read-only client"
        # the only POST is rag/query
        import re
        posts = re.findall(r'api_request\(\s*"POST"\s*,\s*"([^"]+)"', src)
        assert set(posts) <= {"/rag/query"}, f"unexpected POST target(s): {posts}"


class TestAnglesDiscovery:
    """`angles` scaffolds the 5-Ws DISCOVERY mode (fix two Ws, expand the rest).
    Matching (axis-weighted ranking) stays server-side; this only chains searches,
    so it must stay a READ-ONLY, one-framed-call GET, never a matcher of its own."""

    GRID_INTENTS = {"similar", "precedent", "track", "local", "angle"}

    def test_intents_cover_the_two_axis_grid(self):
        assert set(ad.INTENTS) == self.GRID_INTENTS

    def test_every_intent_fixes_two_ws_and_names_corpora(self):
        for intent, (fixed, expand, corpora) in ad.INTENTS.items():
            # a fixed pair names two Ws; corpora is a non-empty comma-list of names
            assert fixed and expand, f"{intent}: axes not fully labeled"
            assert corpora and all(c.strip() for c in corpora.split(",")), f"{intent}: bad corpora"

    def test_angles_is_read_only_one_framed_get_search(self):
        """The whole point of a consumer client: angles must GET /search and nothing
        else. If it ever POSTs or hits another endpoint, discovery has grown a write
        path or a second API surface it shouldn't have."""
        import inspect, re
        src = inspect.getsource(ad.cmd_angles)
        calls = re.findall(r'api_request\(\s*"([A-Z]+)"\s*,\s*"([^"]+)"', src)
        assert calls == [("GET", "/search")], f"angles made unexpected call(s): {calls}"

    def test_intent_choices_are_enforced(self):
        """--intent must be constrained to the grid; a typo should be rejected, not
        silently run an unintended (or blank) intent."""
        r = run("angles", "seed", "--intent", "frobnicate")
        assert r.returncode != 0
        assert "frobnicate" in (r.stdout + r.stderr)

    def test_help_advertises_intent(self):
        r = run("angles", "--help")
        assert r.returncode == 0 and "--intent" in r.stdout

    def test_next_steps_teach_pivoting_the_fixed_pair(self):
        steps = ad._skill_next_steps("angles", _Args(), has_key=True)
        blob = " ".join(a + " " + w for a, w in steps)
        assert "--intent" in blob, "angles should teach re-running with a different intent"
        assert "SECOND axis" in blob, "the corroboration rule should surface in the plan"


class _Args:
    def __init__(self, **kw):
        self.json = False
        self.community = "alaska-news"
        self.corpus = None
        self.limit = 5
        self.seed = "x"
        self.intent = "similar"
        self.since = None
        self.until = None
        self.days = 30
        self.type = None
        self.query = ""
        self.offset = 0
        self.role = None
        self.category = None
        self.sort = "new"
        self.window = None
        self.tag = None
        self.person_id = "pid"
        self.__dict__.update(kw)


class TestHateoasEmitted:
    """The HATEOAS discipline: no dead ends, prioritized next steps with the WHY,
    capped 3-5, and state-driven. This client must EMIT that."""

    MODES = ["digest", "check", "search", "angles", "article", "transcript", "events", "rag",
             "clip", "communities", "people", "person", "topics", "tags", "browse"]

    @pytest.mark.parametrize("mode", MODES)
    def test_every_mode_has_next_steps_no_dead_end(self, mode):
        steps = ad._skill_next_steps(mode, _Args(), has_key=True)
        assert steps, f"{mode} is a dead end: no next steps"

    @pytest.mark.parametrize("mode", MODES)
    def test_next_steps_capped_at_five(self, mode):
        # the guide: >5 needs priority signals; keep it <=5
        assert len(ad._skill_next_steps(mode, _Args(), has_key=True)) <= 5

    @pytest.mark.parametrize("mode", MODES)
    def test_every_next_step_carries_a_reason(self, mode):
        for action, why in ad._skill_next_steps(mode, _Args(), has_key=True):
            assert action and why, f"{mode}: an action or its reason is empty"

    def test_state_driven_no_key_prioritizes_getting_one(self):
        """New/incomplete state -> onboarding action first (guide's state table)."""
        no_key = ad._skill_next_steps("digest", _Args(), has_key=False)
        with_key = ad._skill_next_steps("digest", _Args(), has_key=True)
        assert "NEWS_DESK_API_KEY" in no_key[0][0], "no-key digest must lead with getting a key"
        assert no_key != with_key, "next steps must adapt to whether a key is set"

    def test_footer_has_related_and_see_also(self, capsys):
        """Unit, no network: the footer itself, on any mode."""
        ad._print_hateoas("search", _Args(), None)
        out = capsys.readouterr().out
        assert "Next steps:" in out
        assert "Related modes:" in out
        assert "See also:" in out

    def test_footer_surfaces_the_servers_own_next_steps(self, capsys):
        resp = {"data": {}, "next_steps": [{"rel": "docs", "method": "GET", "href": "/docs/api"}]}
        ad._print_hateoas("search", _Args(), resp)
        out = capsys.readouterr().out
        assert "The API points onward" in out and "/docs/api" in out


class TestHateoasConsumed:
    """It must also CONSUME the server's next_steps rather than ignore them."""

    def test_extracts_server_next_steps_top_level(self):
        resp = {"data": {}, "next_steps": [
            {"rel": "docs", "method": "GET", "href": "/docs/api", "description": "view docs"}]}
        out = ad._server_next_steps(resp)
        assert out and "/docs/api" in out[0] and "GET" in out[0]

    def test_extracts_server_next_steps_nested_under_data(self):
        resp = {"data": {"next_steps": [{"rel": "self", "href": "/articles/1"}]}}
        assert any("/articles/1" in s for s in ad._server_next_steps(resp))

    def test_no_next_steps_is_empty_not_a_crash(self):
        assert ad._server_next_steps({"data": {}}) == []
        assert ad._server_next_steps("not a dict") == []


class TestJsonIsMachineClean:
    def test_emit_json_is_valid_with_no_prose(self, capsys):
        """Unit, no network: --json is the machine surface, so _emit must print
        valid JSON with the license + next-steps prose OMITTED (machines read
        next_steps from the payload). This is also the regression guard for the
        old bug where the license line was appended to JSON and broke parsing."""
        import json as _json
        payload = {"data": {"x": 1}, "next_steps": [{"rel": "self", "href": "/a"}]}
        ad._emit(payload, _Args(json=True), mode="search")
        out = capsys.readouterr().out
        parsed = _json.loads(out)  # raises if prose leaked in
        assert parsed["data"]["x"] == 1 and parsed["next_steps"]
        assert "Next steps:" not in out
        assert "ai-train=no" not in out

    def test_emit_markdown_carries_footer_and_license(self, capsys):
        ad._emit({"data": {}}, _Args(json=False), mode="search")
        out = capsys.readouterr().out
        assert "Next steps:" in out and "ai-train=no" in out

    def test_json_flag_works_after_the_subcommand(self):
        """A CLI user types `digest --json`, not `--json digest`; both the flag and
        --community must parse in that position."""
        r = run("search", "--help")
        assert "--json" in r.stdout and "--community" in r.stdout



class TestNonJsonResponses:
    """Regression: `clip` hits /clips/<id>/stream, which 302s to an MP4. The
    client decoded every 200 as JSON, so the one advertised clip mode died with
    an uncaught UnicodeDecodeError traceback (reproduced 2026-09-09). A research
    client must fail like it documents: status, why, recovery."""

    def test_non_json_payload_raises_apierror_not_a_decode_crash(self, monkeypatch):
        class _Resp:
            status = 200
            def read(self, *a): return b"\x00\x80\xff not json"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        monkeypatch.setattr(ad.urllib.request, "urlopen", lambda *a, **k: _Resp())
        monkeypatch.setenv("ALASKA_DESK_API_KEY", "cn_" + "0" * 40)
        with pytest.raises(ad.ApiError) as ei:
            ad.api_request("GET", "/clips/x/stream")
        assert ei.value.code == ad.NON_JSON

    def test_timeout_is_not_reported_as_unreachable(self, monkeypatch):
        """/rag/query measured 84s against a 60s default: the API was up and the
        client said 'unreachable', sending the reader to debug their network."""
        def _boom(*a, **k):
            raise ad.urllib.error.URLError(TimeoutError("timed out"))
        monkeypatch.setattr(ad.urllib.request, "urlopen", _boom)
        monkeypatch.setenv("ALASKA_DESK_API_KEY", "cn_" + "0" * 40)
        with pytest.raises(ad.ApiError) as ei:
            ad.api_request("POST", "/rag/query")
        assert ei.value.code == ad.TIMED_OUT
        assert "unreachable" not in str(ei.value)

    def test_rag_gets_a_timeout_above_its_measured_latency(self):
        assert ad.RAG_TIMEOUT >= 120, "rag measured 84s; a 60s budget cuts off healthy calls"


class TestEventsAreActuallyUpcoming:
    """Regression: `events` ran /search?corpus=events, which ranks by relevance,
    not date. On 2026-09-09 it returned 15 of 15 events already PAST under a
    heading reading 'upcoming'. A hearing listing that shows only finished
    meetings is worse than none: the whole use is what you can still attend."""

    def test_events_queries_the_date_ranged_endpoint(self):
        import inspect, re
        src = inspect.getsource(ad.cmd_events)
        calls = re.findall(r'api_request\(\s*"([A-Z]+)"\s*,\s*"([^"]+)"', src)
        assert calls == [("GET", "/calendar")], f"events must use /calendar, got {calls}"

    def test_events_window_starts_now_and_runs_forward(self, monkeypatch):
        seen = {}
        def _fake(method, path, params=None, **k):
            seen.update(params or {})
            return {"data": {"events": []}}
        monkeypatch.setattr(ad, "api_request", _fake)
        ad.cmd_events(_Args(days=14, limit=5))
        start, end = seen["start"][:10], seen["end"][:10]
        import datetime as dt
        today = dt.datetime.now(dt.timezone.utc).date()
        assert start == today.isoformat(), "the window must start now, not at an arbitrary date"
        assert end == (today + dt.timedelta(days=14)).isoformat()


class TestWhenAxisIsFilterable:
    """The five-Ws method here is about holding some axes and varying others, and
    When is the only one the server can filter (/search grew date_from/date_to on
    2026-08-14). A client that cannot pass it cannot run its own method."""

    def test_since_and_until_map_to_the_api_params(self):
        got = ad._date_params(_Args(since="2026-01-01", until="2026-06-30"))
        assert got == {"date_from": "2026-01-01", "date_to": "2026-06-30"}

    def test_unset_dates_are_omitted_not_sent_empty(self):
        assert ad._date_params(_Args()) == {}

    @pytest.mark.parametrize("mode", ["search", "angles"])
    def test_both_discovery_modes_accept_the_date_range(self, mode):
        r = run(mode, "--help")
        assert "--since" in r.stdout and "--until" in r.stdout

    def test_search_forwards_the_range(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(ad, "api_request",
                            lambda m, p, params=None, **k: (seen.update(params or {}), {"data": {}})[1])
        ad.cmd_search(_Args(query="x", since="2026-02-01"))
        assert seen.get("date_from") == "2026-02-01"


class TestCorpusHelpMatchesTheApi:
    """The help listed 5 corpora; the API queries 8. Two of the missing three are
    editor/admin only, which is the fact a consumer most needs stated."""

    def test_all_eight_corpora_are_named(self):
        assert len(ad.CORPORA) == 8
        for c in ("articles", "users", "tags", "transcripts", "speakers", "events",
                  "external_documents", "social_post"):
            assert c in ad.CORPORA

    def test_help_names_them_and_flags_the_restricted_pair(self):
        r = run("search", "--help")
        blob = r.stdout.replace("\n", " ")
        assert "social_post" in blob and "external_documents" in blob
        assert "editor/admin" in blob

    def test_restricted_set_is_the_gated_pair(self):
        assert ad.RESTRICTED_CORPORA == {"external_documents", "social_post"}

    def test_a_typo_corpus_is_rejected_not_silently_empty(self):
        r = run("search", "x", "--corpus", "artcles", env={"ALASKA_DESK_API_KEY": "cn_" + "0" * 40})
        assert r.returncode != 0
        blob = r.stdout + r.stderr
        assert "Unknown corpus" in blob and "artcles" in blob
        assert "articles" in blob, "the error should list what IS valid"

    def test_asking_for_a_gated_corpus_warns_first(self, capsys):
        ad._check_corpora("articles,social_post")
        assert "editor/admin only" in capsys.readouterr().err



class TestKeyBlindEndpointsAreNamedAsSuch:
    """`GET /clips` and `/transcripts/search` authenticate by cookie session only
    and reject EVERY api key, admin included (verified 2026-09-09 with an
    elevated newsroom key: both 401). Calling that a role gate sends the reader
    to request a role that cannot help."""

    def test_check_lists_them_as_unreachable_by_any_key(self):
        """Needs a real key, since 2026-09-09, and that is the design not a gap.

        This assertion used to hold with NO key, because `cmd_check` recited a
        hand-written KEY_BLIND_ENDPOINTS constant. Phase D of the platform plan
        deleted that constant and asks `GET /api/v1/me` instead, which is the
        whole point: the list is now derived from the router that serves the
        endpoints and cannot go stale. Deriving it costs a credential.

        `run()` blanks ALASKA_DESK_API_KEY on purpose to isolate from .env.local,
        so this test was structurally unable to pass after that change and failed
        for a week's worth of runs that nobody made. Pass the key explicitly and
        skip when the environment has none, rather than asserting a keyless
        behaviour the client deliberately no longer has.
        """
        import os
        key = os.environ.get("ALASKA_DESK_API_KEY", "")
        if not key:
            pytest.skip("needs ALASKA_DESK_API_KEY: the list is served, not recited")
        r = run("check", env={"ALASKA_DESK_API_KEY": key})
        if "reachability: unavailable" in r.stdout:
            pytest.skip("platform predates GET /api/v1/me reachability")
        assert "Not reachable by ANY api key" in r.stdout
        # Derived from the router, so assert the PATH the server returns rather
        # than the human label the deleted constant used to carry.
        assert "/api/v1/clips" in r.stdout

    def test_they_are_not_probed_as_if_a_role_could_fix_them(self):
        probed = [label for label, *_ in ad.keyed_probes("alaska-news")]
        assert "clips (browse)" not in probed

    def test_403_recovery_no_longer_blames_a_clip_role(self):
        import inspect
        src = inspect.getsource(ad._guided)
        assert "browsing clips" not in src


class TestRenderedByDefault:
    """SKILL.md promises 'rendered markdown by default'. article-by-id and rag
    passed no renderer, so both dumped raw JSON with no --json asked for (rag's
    was 33KB)."""

    def test_rag_renders_answer_and_citations(self, monkeypatch, capsys):
        monkeypatch.setattr(ad, "api_request", lambda *a, **k: {"data": {
            "mode": "synthesized", "answer": "The port got $180M.",
            "citations": [{"ref": "F1", "kind": "fact", "verbatim_excerpt": "a quote",
                           "url": "https://example.org/a"}]}})
        ad.cmd_rag(_Args(query="port", limit=8))
        out = capsys.readouterr().out
        assert "The port got $180M." in out and "citations" in out and "F1" in out
        assert "https://example.org/a" in out, "a citation without its url is not attributable"
        assert not out.lstrip().startswith("{"), "rag must not dump raw JSON by default"

    def test_article_by_id_is_not_a_raw_dump(self, monkeypatch, capsys):
        monkeypatch.setattr(ad, "api_request", lambda *a, **k: {"data": {
            "title": "A headline", "slug": "a-headline", "published_at": "2026-09-01T00:00:00Z",
            "tldr": "the gist", "content": "the body"}})
        ad.cmd_article(_Args(ref="4f0b1e2a-0000-0000-0000-000000000000"))
        out = capsys.readouterr().out
        assert out.lstrip().startswith("# A headline")
        assert "the gist" in out and "the body" in out


class TestCommunityDiscovery:
    """--community took a slug and nothing told you which slugs exist, so the
    only discoverable value was the default baked into the source."""

    def test_communities_mode_exists_and_is_read_only(self):
        import inspect, re
        src = inspect.getsource(ad.cmd_communities)
        assert re.findall(r'api_request\(\s*"([A-Z]+)"', src) == ["GET"]

    def test_it_renders_slugs_and_marks_the_default(self, monkeypatch, capsys):
        monkeypatch.setattr(ad, "api_request", lambda *a, **k: {"data": [
            {"slug": "alaska-news", "name": "Alaska News"}, {"slug": "other", "name": "Other"}]})
        ad.cmd_communities(_Args())
        out = capsys.readouterr().out
        assert "alaska-news" in out and "other" in out and "default" in out


class TestClipResolvesRatherThanDownloads:
    def test_clip_does_not_follow_the_redirect(self):
        import inspect
        src = inspect.getsource(ad.cmd_clip)
        assert "api_redirect" in src, "clip must resolve the 302, not follow it into video bytes"
        assert "api_request" not in src

    def test_relative_location_is_resolved_to_something_fetchable(self, monkeypatch):
        def _boom(*a, **k):
            raise ad.urllib.error.HTTPError(
                "https://alaskanews.com/api/v1/clips/x/stream", 302,
                "Found", {"Location": "/storage/clip.mp4"}, None)
        monkeypatch.setattr(ad.urllib.request, "build_opener",
                            lambda *a, **k: type("O", (), {"open": staticmethod(_boom)})())
        monkeypatch.setenv("ALASKA_DESK_API_KEY", "cn_" + "0" * 40)
        out = ad.api_redirect("/clips/x/stream")
        assert out["location"].startswith("http"), "a relative Location must be made absolute"



class TestReadSurfaceCoverage:
    """The four surfaces the 2026-09-09 audit left unwrapped: persons, tags,
    topics and the article list. Each is a GET, and each must STAY one."""

    @pytest.mark.parametrize("fn,path", [
        ("cmd_people", "/persons"), ("cmd_topics", "/topics"),
        ("cmd_tags", "/tags"), ("cmd_browse", "/articles"),
    ])
    def test_each_new_mode_is_a_single_read(self, fn, path):
        import inspect, re
        src = inspect.getsource(getattr(ad, fn))
        calls = re.findall(r'api_request\(\s*"([A-Z]+)"', src)
        assert calls and set(calls) == {"GET"}, f"{fn} made a non-GET call: {calls}"

    def test_person_makes_exactly_two_reads_record_then_coverage(self):
        import inspect, re
        src = inspect.getsource(ad.cmd_person)
        assert re.findall(r'api_request\(\s*"([A-Z]+)"', src) == ["GET", "GET"]

    def test_feed_is_deliberately_not_wrapped(self):
        """/feed returns byte-identical results to /articles?sort=new and takes no
        community param (checked 2026-09-09), so wrapping it would add a mode with
        strictly less reach. If someone adds it later, they should have to delete
        this test and read why first."""
        src = Path(SCRIPT).read_text()
        assert '"/feed"' not in src


class TestPersonRecordUnwrapping:
    """GET /persons/<id> nests the record under data.speaker, unlike the LIST
    endpoint which returns person objects directly. Reading data directly showed
    the raw uuid as the heading and dropped role, bio and organization."""

    PAYLOAD = {"data": {"speaker": {"display_name": "Mike Dunleavy", "role": "Governor",
                                    "organization": "State of Alaska", "bio": "a bio"},
                        "aliases": [{"alias": "Governor Dunleavy"}]}}

    def _run(self, monkeypatch, capsys, coverage):
        calls = iter([self.PAYLOAD, coverage])
        monkeypatch.setattr(ad, "api_request", lambda *a, **k: next(calls))
        ad.cmd_person(_Args(person_id="x", limit=5))
        return capsys.readouterr().out

    def test_name_role_and_aliases_render(self, monkeypatch, capsys):
        out = self._run(monkeypatch, capsys, {"data": [], "total": 0})
        assert out.lstrip().startswith("# Mike Dunleavy")
        assert "Governor" in out and "State of Alaska" in out
        assert "Governor Dunleavy" in out, "aliases are how you search for someone"

    def test_structural_links_are_not_called_quotes(self, monkeypatch, capsys):
        """The endpoint returns attribution name-matches UNION structured links.
        Only the first kind carries a verbatim excerpt. Labelling the union
        'quoted in' would invite attributing words nobody recorded them saying."""
        out = self._run(monkeypatch, capsys, {"data": [
            {"title": "A story", "id": "1", "verbatim_excerpt": None, "attribution_count": 0}],
            "total": 1})
        assert "appears in" in out and "quoted in" not in out
        assert "structural links rather than matched quotes" in out

    def test_a_real_quote_is_marked_as_quoted(self, monkeypatch, capsys):
        out = self._run(monkeypatch, capsys, {"data": [
            {"title": "A story", "id": "1", "verbatim_excerpt": "we will fund it",
             "attribution_count": 3}], "total": 1})
        assert "quoted (3x)" in out and "we will fund it" in out
        assert "structural links rather than" not in out


class TestTopicCountsAreNotFakedAsZero:
    """/topics returns article_count / source_count / total_views and on
    2026-09-09 every one of the 15 topics reported 0 for all three. Printing
    '0 articles' against a beat that has coverage reads as 'nothing published
    here', which is the same lie an empty result set tells."""

    def _render(self, monkeypatch, capsys, rows):
        monkeypatch.setattr(ad, "api_request", lambda *a, **k: {"data": rows})
        ad.cmd_topics(_Args(limit=10))
        return capsys.readouterr().out

    def test_all_zero_counts_are_suppressed_and_explained(self, monkeypatch, capsys):
        out = self._render(monkeypatch, capsys, [
            {"name": "Health", "slug": "health", "article_count": 0, "source_count": 0}])
        # Assert on the topic's own ROW, not the whole page: the note that
        # explains the suppression necessarily quotes the phrase it suppresses.
        row = next(ln for ln in out.splitlines() if ln.startswith("- Health"))
        assert "0 articles" not in row and "0 sources" not in row
        assert "not being populated" in out and "UNKNOWN" in out

    def test_real_counts_are_shown_when_the_platform_populates_them(self, monkeypatch, capsys):
        out = self._render(monkeypatch, capsys, [
            {"name": "Health", "slug": "health", "article_count": 12, "source_count": 3}])
        assert "12 articles" in out
        assert "not being populated" not in out


class TestPagingIsReachable:
    """List endpoints answer {data, count, offset, limit, has_more}. Reporting
    has_more without offering --offset states a fact the caller cannot act on."""

    @pytest.mark.parametrize("mode", ["people", "topics", "tags", "browse", "person"])
    def test_list_modes_take_an_offset(self, mode):
        r = run(mode, "--help")
        assert "--offset" in r.stdout, f"{mode} cannot reach past its first page"

    def test_has_more_names_the_next_offset(self):
        line = ad._paged({"data": [], "count": 3, "offset": 0, "limit": 3,
                          "has_more": True, "total": 10})
        assert "1-3 of 10" in line and "--offset 3" in line

    def test_last_page_offers_no_next(self):
        assert "--offset" not in ad._paged(
            {"count": 2, "offset": 8, "limit": 10, "has_more": False, "total": 10})

    def test_a_non_list_response_gets_no_pagination_line(self):
        assert ad._paged({"data": {"title": "x"}}) == ""


class TestBrowseRouting:
    def test_tag_filter_uses_the_tag_articles_route(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(ad, "api_request",
                            lambda m, p, params=None, **k: (seen.update({"p": p}), {"data": []})[1])
        ad.cmd_browse(_Args(tag="transportation", limit=5))
        assert seen["p"] == "/tags/transportation/articles"

    def test_without_a_tag_it_browses_the_community(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(ad, "api_request",
                            lambda m, p, params=None, **k: (seen.update({"p": p, "q": params}), {"data": []})[1])
        ad.cmd_browse(_Args(limit=5, sort="new"))
        assert seen["p"] == "/articles"
        assert seen["q"]["community"] == "alaska-news" and seen["q"]["sort"] == "new"

    def test_sort_choices_are_enforced(self):
        r = run("browse", "--sort", "sideways")
        assert r.returncode != 0 and "sideways" in (r.stdout + r.stderr)



class TestReachabilityRender:
    """GET /me's reachability block, rendered.

    These need no credential ON PURPOSE. The end-to-end test of this path skips
    without a key, which means CI never runs it, which is how the first version
    of this feature shipped with `read_only` unread and a 200-with-no-block
    rendering as "auth method: ?"."""

    FULL = {
        "auth_method": "api_key", "read_only": False,
        "communities": [{"slug": "alaska-news", "role": "admin"}],
        "reachable_count": 196, "conditional_count": 15,
        "reachable": ["/api/v1/articles"],
        "unreachable": [
            {"path": "/api/v1/clips", "reason": "session_auth_only",
             "remedy": "No API key reaches this endpoint, whatever its role."},
            {"path": "/api/v1/transcript/{sourceId}/speakers", "reason": "session_auth_only"},
            {"path": "/api/v1/admin/thing", "reason": "requires_platform_admin"},
            {"path": "/api/v1/articles/{id}/publish", "reason": "requires_role"},
        ],
    }

    def _txt(self, reach):
        return "\n".join(ad.render_reachability(reach))

    def test_counts_and_auth_method(self):
        out = self._txt(self.FULL)
        assert "api_key" in out and "196" in out and "15" in out

    def test_a_writable_key_is_told_it_could_be_read_only(self):
        """SKILL.md tells the reader to tick Read-only when creating a key. The
        server now reports whether they did, and saying nothing wastes the only
        field that closes that loop."""
        out = self._txt(self.FULL)
        assert "NOT read-only" in out and "profile/settings" in out

    def test_a_read_only_key_is_confirmed_and_warned_about_rag(self):
        out = self._txt({**self.FULL, "read_only": True})
        assert "READ-ONLY" in out
        assert "POST" in out, "rag is a POST and a read-only key refuses it"
        assert "NOT read-only" not in out

    def test_each_reason_is_grouped_not_merged(self):
        out = self._txt(self.FULL)
        assert "Not reachable by ANY api key (2)" in out
        assert "/api/v1/clips" in out
        assert "editor/admin membership (1)" in out
        assert "platform admin (1)" in out

    def test_the_servers_remedy_is_shown_not_discarded(self):
        assert "whatever its role" in self._txt(self.FULL)

    def test_membership_role_is_surfaced(self):
        assert "alaska-news" in self._txt(self.FULL) and "admin" in self._txt(self.FULL)

    def test_an_unknown_reason_is_still_reported(self):
        """A reason this client has never heard of must not vanish silently: the
        whole point of asking the server is that it knows things we do not."""
        out = self._txt({**self.FULL, "unreachable": [
            {"path": "/api/v1/future", "reason": "some_new_gate"}]})
        assert "some_new_gate" in out and "/api/v1/future" in out

    def test_a_missing_block_reads_as_missing_not_as_unknown_values(self):
        """A 200 with no reachability is an older platform build, not an empty
        answer. Rendering it as 'auth method: ?' presents a missing FEATURE as a
        missing VALUE, which sends the reader to look at their key."""
        for empty in (None, {}, "not a dict"):
            out = self._txt(empty)
            assert "not reported by this platform build" in out
            assert "auth method: ?" not in out

    def test_rag_is_no_longer_probed(self):
        """/me reports rag's reachability, and probing it meant an 84s synthesis
        call on every `check`."""
        assert not any(p == "/rag/query" for _, _, p, _, _ in ad.keyed_probes("x"))



class TestNewsroomAgnostic:
    """Alaska is the DEFAULT, not the design. Four constants kept this client
    Alaska-only; they are configuration now, so a second newsroom on the same
    platform is a setting rather than a fork."""

    def test_site_and_community_come_from_env(self, monkeypatch):
        monkeypatch.setenv("NEWS_SITE", "https://example.news/")
        monkeypatch.setenv("NEWS_COMMUNITY", "elsewhere")
        assert ad.site() == "https://example.news", "a trailing slash must not double up"
        assert ad.default_community() == "elsewhere"

    def test_defaults_are_still_alaska(self, monkeypatch):
        monkeypatch.delenv("NEWS_SITE", raising=False)
        monkeypatch.delenv("NEWS_COMMUNITY", raising=False)
        assert ad.site() == "https://alaskanews.com"
        assert ad.default_community() == "alaska-news"

    def test_api_base_is_derived_from_the_site(self, monkeypatch):
        monkeypatch.delenv("PLATFORM_API_BASE", raising=False)
        monkeypatch.setenv("NEWS_SITE", "https://example.news")
        assert ad.api_base() == "https://example.news/api/v1"

    def test_platform_api_base_still_overrides_outright(self, monkeypatch):
        monkeypatch.setenv("NEWS_SITE", "https://example.news")
        monkeypatch.setenv("PLATFORM_API_BASE", "http://127.0.0.1:9/v2")
        assert ad.api_base() == "http://127.0.0.1:9/v2"

    def test_the_old_key_env_still_works(self, monkeypatch):
        """Renaming it without honouring the old name would break every existing
        setup silently, reported as 'no key set'."""
        monkeypatch.delenv("NEWS_DESK_API_KEY", raising=False)
        monkeypatch.setenv("ALASKA_DESK_API_KEY", "cn_legacy")
        assert ad.read_key() == "cn_legacy"

    def test_the_new_key_env_wins_when_both_are_set(self, monkeypatch):
        monkeypatch.setenv("ALASKA_DESK_API_KEY", "cn_old")
        monkeypatch.setenv("NEWS_DESK_API_KEY", "cn_new")
        assert ad.read_key() == "cn_new"

    def test_no_market_is_compiled_into_a_request_path(self, monkeypatch):
        """The probes hard-coded `alaska-news`, so `check --community X` reported
        on Alaska while saying it had checked X."""
        for _, _, _, params, _ in ad.keyed_probes("elsewhere"):
            if params and "community" in params:
                assert params["community"] == "elsewhere"

    def test_see_also_follows_the_configured_newsroom(self, monkeypatch):
        monkeypatch.setenv("NEWS_SITE", "https://example.news")
        assert "example.news" in ad.see_also() and "alaskanews" not in ad.see_also()


class TestTermsAreReadNotAsserted:
    """The terms line is printed under someone else's reporting, and the
    attribution is the consideration for using it. Getting it from a constant
    meant a second newsroom would have had Alaska's terms published over its
    work."""

    ROBOTS = "User-agent: *\nContent-Signal: ai-train=no, search=yes, ai-input=yes\nAllow: /\n"
    LLMS = "Our robots.txt declares:\n\n- `ai-train=yes` do whatever\n- `ai-input=no` nope\n"

    def _serve(self, monkeypatch, bodies):
        """bodies: {path: text}; a path absent from the dict raises, as a 404 would."""
        class _R:
            def __init__(self, t): self.t = t
            def read(self, *a): return self.t.encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def _open(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            for path, text in bodies.items():
                if url.endswith(path):
                    return _R(text)
            raise ad.urllib.error.URLError("not found")
        monkeypatch.setattr(ad, "_TERMS_CACHE", {})
        monkeypatch.setattr(ad.urllib.request, "urlopen", _open)

    def test_robots_content_signal_is_preferred(self, monkeypatch):
        self._serve(monkeypatch, {"/robots.txt": self.ROBOTS, "/llms.txt": self.LLMS})
        assert ad.content_signal("https://x.test") == "ai-train=no, search=yes, ai-input=yes"

    def test_llms_txt_is_the_fallback(self, monkeypatch):
        self._serve(monkeypatch, {"/llms.txt": self.LLMS})
        got = ad.content_signal("https://x.test")
        assert "ai-train=yes" in got and "ai-input=no" in got

    def test_a_different_newsroom_gets_ITS_terms_not_alaskas(self, monkeypatch):
        """The whole point. A newsroom that permits training and forbids quoting
        must not have Alaska's opposite stance printed under its work."""
        monkeypatch.setenv("NEWS_SITE", "https://other.news")
        self._serve(monkeypatch, {"/llms.txt": self.LLMS})
        note = ad.terms_note()
        assert "other.news" in note
        assert "ai-train=yes" in note
        assert "Do not train on it." not in note
        assert "Quote with attribution" not in note, "ai-input=no must not invite quoting"

    def test_unreadable_terms_are_declared_not_invented(self, monkeypatch):
        """A tool that cannot read the terms has no business asserting them, and
        the old constant asserted them unconditionally."""
        monkeypatch.setenv("NEWS_SITE", "https://silent.test")
        self._serve(monkeypatch, {})
        note = ad.terms_note()
        assert "could NOT be read" in note
        assert "ai-train" not in note, "no stance may be invented when none was readable"
        assert "attribute with a backlink regardless" in note

    def test_the_signal_is_fetched_once_per_site(self, monkeypatch):
        calls = []
        self._serve(monkeypatch, {"/robots.txt": self.ROBOTS})
        real = ad.urllib.request.urlopen
        monkeypatch.setattr(ad.urllib.request, "urlopen",
                            lambda r, timeout=None: (calls.append(1), real(r, timeout))[1])
        ad.content_signal("https://x.test"); ad.content_signal("https://x.test")
        assert len(calls) == 1, "every rendered mode prints this; refetching per mode is waste"



# --------------------------------------------------------------------------
# The SKILL.md document itself.
#
# Everything above this line tests the Python client. Nothing tested the file
# that IS the skill, which is what an agent actually loads, and which had
# already drifted: `check` was a registered mode absent from the Modes block.
#
# Constraints below come from the Agent Skills specification at
# https://agentskills.io/specification, not from taste.
# --------------------------------------------------------------------------

SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"


def _frontmatter():
    """Parse SKILL.md's YAML frontmatter without a YAML dependency.

    The client is stdlib-only and its tests should not be the thing that drags
    PyYAML in. This handles exactly the three shapes the file uses: `key: value`,
    `key: >-` with an indented folded block, and `key:` with an indented map."""
    text = SKILL_MD.read_text()
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    body = text.split("---\n", 2)[1]
    out, key, folded, mapping = {}, None, [], None
    for raw in body.splitlines():
        if not raw.strip():
            continue
        indented = raw.startswith("  ")
        if indented and key and folded is not None:
            folded.append(raw.strip())
            continue
        if indented and mapping is not None:
            k, _, v = raw.strip().partition(":")
            mapping[k.strip()] = v.strip().strip('"').strip("'")
            continue
        if key and folded:
            out[key] = " ".join(folded)
        key, folded, mapping = None, None, None
        k, _, v = raw.partition(":")
        k, v = k.strip(), v.strip()
        if v in (">-", "|", ">"):
            key, folded = k, []
        elif v == "":
            mapping = out.setdefault(k, {})
        else:
            out[k] = v.strip('"').strip("'")
    if key and folded:
        out[key] = " ".join(folded)
    return out


class TestSkillMdMeetsTheSpec:
    """https://agentskills.io/specification, the standard this repo declares."""

    def test_required_fields_are_present(self):
        fm = _frontmatter()
        assert fm.get("name"), "name is required"
        assert fm.get("description"), "description is required"

    def test_name_matches_the_spec_constraints(self):
        """Max 64 characters. Lowercase letters, numbers and hyphens only. Must
        not start or end with a hyphen."""
        name = _frontmatter()["name"]
        assert len(name) <= 64, f"name is {len(name)} chars, spec max is 64"
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name), \
            f"{name!r} is not lowercase-hyphen-only, or starts/ends with a hyphen"

    def test_description_is_within_the_spec_limit(self):
        d = _frontmatter()["description"]
        assert d.strip(), "description must be non-empty"
        assert len(d) <= 1024, f"description is {len(d)} chars, spec max is 1024"

    def test_compatibility_is_within_the_spec_limit(self):
        c = _frontmatter().get("compatibility", "")
        assert len(c) <= 500, f"compatibility is {len(c)} chars, spec max is 500"

    def test_metadata_is_a_flat_string_map(self):
        """Spec: 'a map from string keys to string values'. A nested structure
        here parses for us and is invalid for a stricter client."""
        md = _frontmatter().get("metadata", {})
        assert isinstance(md, dict) and md, "metadata should carry the extras"
        for k, v in md.items():
            assert isinstance(k, str) and isinstance(v, str), f"{k}={v!r} is not string to string"

    def test_declared_license_matches_the_bundled_one(self):
        """`license` is a spec field. Declaring one the repo does not ship is
        worse than declaring none, because it is checkable and wrong."""
        declared = _frontmatter().get("license", "")
        assert declared, "license should be declared for a skill meant to be installed"
        bundled = (SKILL_MD.parent.parent.parent / "LICENSE").read_text()
        assert declared.lower() in bundled.lower().split("\n")[0].lower(), \
            f"frontmatter says {declared!r}, LICENSE says {bundled.splitlines()[0]!r}"


class TestSkillMdMatchesTheCode:
    """The drift catcher. SKILL.md is prose about a program, and the whole of
    the 2026-09-09 audit was prose that had stopped being true."""

    MODES_RE = re.compile(r"^## Modes$.*?^```bash\n(.*?)^```", re.M | re.S)

    def _documented_modes(self):
        m = self.MODES_RE.search(SKILL_MD.read_text())
        assert m, "SKILL.md has no '## Modes' block with a bash fence"
        return {line.split()[2] for line in m.group(1).splitlines()
                if line.startswith("python3 scripts/news_desk.py ") and len(line.split()) > 2}

    def _registered_modes(self):
        src = Path(SCRIPT).read_text()
        return set(re.findall(r'sub\.add_parser\(\s*"([a-z]+)"', src))

    def test_every_registered_mode_is_documented(self):
        missing = self._registered_modes() - self._documented_modes()
        assert not missing, f"modes the CLI has and the Modes block omits: {sorted(missing)}"

    def test_every_documented_mode_exists(self):
        """The other direction: a mode removed from the code but left in the
        docs sends a reader to a command that errors."""
        extra = self._documented_modes() - self._registered_modes()
        assert not extra, f"modes documented but not registered: {sorted(extra)}"

    def test_the_readme_lists_every_mode_too(self):
        """The README carries its own mode list and a count. It drifts by exactly
        the same mechanism SKILL.md did, and a reader who never opens SKILL.md
        sees only this one."""
        readme = (SKILL_MD.parent.parent.parent / "README.md").read_text()
        missing = sorted(m for m in self._registered_modes() if f"`{m}`" not in readme)
        assert not missing, f"modes the CLI has and the README omits: {missing}"
        n = len(self._registered_modes())
        assert f"{n} modes" in readme, f"README should say '{n} modes'; the count moved"

    def test_the_script_it_names_exists(self):
        for ref in re.findall(r"scripts/([a-z_]+\.py)", SKILL_MD.read_text()):
            assert (SKILL_MD.parent / "scripts" / ref).exists(), f"SKILL.md names a missing {ref}"

    def test_the_read_only_contract_is_stated(self):
        """This skill's one hard promise, asserted as a POSITIVE claim.

        The first version of this test scanned for write verbs and called any
        line containing one a contradiction. It fired immediately on a sentence
        describing the SERVER rejecting writes, which is the promise being kept,
        not broken. An extractor that cannot tell an explanation from an
        advertisement reports the fix as the defect, which is the hazard
        live-neon's own scanner documents. The code-side contract is enforced by
        TestReadOnlyContract, which reads the source rather than the prose."""
        text = SKILL_MD.read_text()
        assert "READ ONLY" in text or "read-only" in text.lower(), \
            "SKILL.md must state the read-only direction somewhere"
        assert "never submits" in text or "only consumes" in text.lower(), \
            "SKILL.md must say plainly that it does not write back"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
