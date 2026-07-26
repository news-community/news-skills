#!/usr/bin/env python3
"""
Offline tests for alaska_desk.py.

The live API needs a per-user cn_ key, so the network path is unverified here (as
with any live-network path). Everything that does NOT touch the network is tested:
arg parsing, URL/param construction, the license reminder, and that keyed modes
fail with guidance rather than a traceback.

    python3 -m pytest test_alaska_desk.py -q
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alaska_desk as ad  # noqa: E402

SCRIPT = str(Path(__file__).resolve().parent / "alaska_desk.py")


def run(*args, env=None):
    import os
    e = dict(os.environ)
    # Isolate from .env.local: popping is NOT enough, because the script's own
    # _load_env() re-reads the file and setdefault()s the key back in. Setting it
    # to "" blocks that (the key "exists" so setdefault won't override) and reads
    # as no-key. A test wanting a specific key overrides via env=.
    e["ALASKA_DESK_API_KEY"] = ""
    if env:
        e.update(env)
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=e)


class TestLicenseDiscipline:
    def test_license_note_names_the_terms(self):
        for term in ("ai-train=no", "attribution", "backlink"):
            assert term in ad.LICENSE_NOTE

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
            ("rag", ["q"]), ("clip", ["clip-id"]),
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
        assert "ALASKA_DESK_API_KEY" in blob
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
        self.__dict__.update(kw)


class TestHateoasEmitted:
    """The HATEOAS discipline: no dead ends, prioritized next steps with the WHY,
    capped 3-5, and state-driven. This client must EMIT that."""

    MODES = ["digest", "check", "search", "angles", "article", "transcript", "events", "rag", "clip"]

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
        assert "ALASKA_DESK_API_KEY" in no_key[0][0], "no-key digest must lead with getting a key"
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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
