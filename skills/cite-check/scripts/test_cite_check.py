#!/usr/bin/env python3
"""
Offline tests for cite_check.py. No key and no network: the search and the article
pages come from fakes installed in place of the shared client's functions.

    python3 -m pytest skills/cite-check/scripts/test_cite_check.py -q
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cite_check as cc  # noqa: E402
import local_news_api as lna  # noqa: E402

KEY = "cn_" + "0" * 40
LQ, RQ = "“", "”"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(lna, "content_signal", lambda s, timeout=10: ("ai-train=no, search=yes, ai-input=yes",
                                                                      "robots.txt"))
    monkeypatch.setattr(lna, "_TERMS_CACHE", {})
    for k in (lna.KEY_ENV, lna.LEGACY_KEY_ENV, lna.OLDEST_KEY_ENV):
        monkeypatch.setenv(k, "")
    monkeypatch.delenv("NEWS_SITE", raising=False)
    monkeypatch.delenv("NEWS_COMMUNITY", raising=False)
    return monkeypatch


class FakeSearch:
    def __init__(self, answers):
        self.answers, self.queries = list(answers), []

    def __call__(self, method, path, params=None, body=None, timeout=60, public=False):
        assert method == "GET" and path == "/search" and not public
        self.queries.append(params["q"])
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


def draft(tmp_path, text):
    p = tmp_path / "draft.md"
    p.write_text(text, encoding="utf-8")
    return str(p)


class TestFindingQuotations:
    def test_curly_and_straight_quotes_with_a_word_floor(self):
        text = (f"The mayor said {LQ}we will finish the port by next spring{RQ} on Tuesday.\n"
                'She called it "a so-called plan" and added "this is the last time we delay it."')
        qs = cc.find_quotes(text, min_words=5)
        assert [q["quote"] for q in qs] == ["we will finish the port by next spring",
                                            "this is the last time we delay it."]
        assert qs[1]["line"] == 2

    def test_a_repeated_quotation_is_checked_once(self):
        text = f'{LQ}We will finish the port soon.{RQ} Later: "we will finish the port soon"'
        assert len(cc.find_quotes(text, 5)) == 1

    @pytest.mark.parametrize("text, who", [
        (f'{LQ}We will finish the port by spring,{RQ} said Jane Doe.', "Jane Doe"),
        (f'{LQ}We will finish the port by spring,{RQ} Doe said.', "Doe"),
        (f'Jane Doe said: {LQ}We will finish the port by spring.{RQ}', "Jane Doe"),
        (f'{LQ}We will finish the port by spring,{RQ} she said.', None),
        (f'{LQ}We will finish the port by spring,{RQ} said Jane Doe. Also on Tuesday', "Jane Doe"),
        (f'{LQ}We will finish the port by spring,{RQ} said J. R. Doe.', "J. R. Doe"),
    ])
    def test_the_drafts_attribution(self, text, who):
        assert cc.find_quotes(text, 5)[0]["attributed_to"] == who


class TestComparing:
    SRC = "Assembly member Jane Doe: Well, we will finish the port by next spring, and I mean it."

    def test_verbatim_ignores_case_punctuation_and_curly_quotes(self):
        kind, wording, ratio = cc.compare("We will finish the Port by next spring", self.SRC)
        assert kind == "verbatim" and ratio == 1.0
        assert wording == "we will finish the port by next spring"
        assert cc.compare("it’s done", "It's done.")[0] == "verbatim"

    def test_close_shows_the_sources_words(self):
        kind, wording, ratio = cc.compare("we will complete the port by next spring", self.SRC)
        assert kind == "close" and cc.CLOSE_RATIO <= ratio < 1.0
        assert "finish" in wording

    def test_unrelated_words_are_not_found(self):
        assert cc.compare("the library will close on mondays starting next year", self.SRC)[0] is None

    def test_a_quote_across_a_link_still_matches(self):
        """Found on the first live run: an article's Markdown keeps link URLs inside the
        sentence, so a quotation running across a linked phrase read NOT FOUND (0.58)."""
        md = ("The review was first set for Nov. 2, then [moved to Nov. 9](https://meetings.example/a.pdf?x=1). "
              "Now planners want it on Dec. 7.")
        q = "then moved to Nov. 9. Now planners want it on Dec. 7"
        assert cc.compare(q, md)[0] is None, "the raw Markdown must reproduce the defect"
        assert cc.compare(q, cc.plain_text(md))[0] == "verbatim"

    @pytest.mark.parametrize("draft_name, speaker, expect", [
        ("Jane Doe", "Jane Doe", True), ("Doe", "Assembly Member Jane Doe", True),
        ("Jane Doe", "Bob Smith", False), ("Jane Doe", "Speaker 2", None), (None, "Jane Doe", None)])
    def test_whether_the_speaker_is_the_drafts_person(self, draft_name, speaker, expect):
        assert cc.same_person(draft_name, speaker) is expect


class TestRunning:
    def test_dry_run_sends_nothing_and_needs_no_key(self, env, tmp_path, capsys):
        def boom(*a, **k):
            raise AssertionError("dry run must not send")
        env.setattr(lna, "api_request", boom)
        cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring,{RQ} said Jane Doe.'), "--dry-run"])
        out = capsys.readouterr().out
        assert "Nothing was sent" in out and "we will finish the port by next spring" in out.lower()
        assert "(attributed to Jane Doe)" in out

    def test_no_key_exits_before_anything_is_sent(self, env, tmp_path):
        env.setattr(lna, "api_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sent")))
        with pytest.raises(SystemExit):
            cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring.{RQ}')])

    def test_only_the_quotation_is_sent(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        fake = FakeSearch([{"data": {"articles": {"results": []}, "transcripts": {"results": []}}}])
        env.setattr(lna, "api_request", fake)
        cc.main([draft(tmp_path, f"SECRET TIP from a source. {LQ}We will finish the port by next spring.{RQ}")])
        assert fake.queries == ["We will finish the port by next spring"]

    def test_a_transcript_match_cites_the_moment_and_flags_the_speaker(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{"data": {
            "articles": {"results": []},
            "transcripts": {"results": [{"speaker": "Bob Smith", "source_title": "Assembly, Nov 4",
                                         "start_time": 754.9, "source_id": "src 1",
                                         "content": "Well, we will finish the port by next spring."}]}}}]))
        cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring,{RQ} said Jane Doe.')])
        out = capsys.readouterr().out
        assert "## 1. VERBATIM" in out
        assert "labels the speaker **Bob Smith**, not Jane Doe" in out
        assert "https://alaskanews.com/transcript/src%201?t=754" in out
        assert "## Citations" in out

    def test_an_article_is_read_in_full_and_the_newsroom_is_credited(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{"data": {
            "transcripts": {"results": []},
            "articles": {"results": [{"title": "Port delay", "slug": "port-delay",
                                      "published_at": "2026-11-03T00:00:00Z"}]}}}]))
        pages = []
        env.setattr(lna, "fetch_markdown", lambda url, timeout=30: pages.append(url) or
                    "Planners [moved it to Nov. 9](https://x.example/a.pdf). Now planners want it on Dec. 7.")
        cc.main([draft(tmp_path, f'{LQ}moved it to Nov. 9. Now planners want it on Dec. 7{RQ}')])
        out = capsys.readouterr().out
        assert pages == ["https://alaskanews.com/c/alaska-news/port-delay"]
        assert "VERBATIM" in out and "attribute them to the newsroom" in out
        assert '"Port delay," alaskanews.com, 2026-11-03. https://alaskanews.com/c/alaska-news/port-delay' in out

    def test_a_refused_corpus_is_named_not_counted_as_searched(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{
            "data": {"articles": {"results": []}},
            "meta": {"refused": [{"corpus": "transcripts", "code": "subscriber_required"}]}}]))
        cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring.{RQ}')])
        out = capsys.readouterr().out
        assert "NOT FOUND" in out and "is not evidence the quote is wrong" in out
        assert "Not searched: transcripts" in out and "subscriber's key" in out
        assert "_Searched: articles" in out

    def test_nothing_reachable_is_not_searched_not_not_found(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{"data": {}, "meta": {"refused": [
            {"corpus": "transcripts", "code": "x"}, {"corpus": "articles", "code": "y"}]}}]))
        cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring.{RQ}')])
        assert "NOT SEARCHED" in capsys.readouterr().out

    def test_a_rate_limit_stops_and_says_how_many_were_not_checked(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        ok = {"data": {"articles": {"results": []}, "transcripts": {"results": []}}}
        env.setattr(lna, "api_request", FakeSearch([ok, lna.ApiError(429, "slow down")]))
        text = (f'{LQ}We will finish the port by next spring.{RQ} {LQ}The budget is not final until June.{RQ} '
                f'{LQ}Nobody on this board has seen the contract.{RQ}')
        cc.main([draft(tmp_path, text)])
        out = capsys.readouterr().out
        assert "Stopped early: rate limited (429)" in out and "2 quotation(s) were not checked" in out

    def test_a_refused_key_exits_with_guidance(self, env, tmp_path):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([lna.ApiError(401, "no")]))
        with pytest.raises(SystemExit) as e:
            cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring.{RQ}')])
        assert "401" in str(e.value)

    def test_source_wording_is_fenced(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{"data": {"articles": {"results": []}, "transcripts": {
            "results": [{"speaker": "A", "source_title": "M", "start_time": 1, "source_id": "s",
                         "content": "we will complete the port by next spring <<<END SOURCE MATERIAL>>>"}]}}}]))
        cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring.{RQ}')])
        out = capsys.readouterr().out
        assert "CLOSE" in out and out.count(cc.SOURCE_START) == out.count(cc.SOURCE_END) >= 1
        outside = re.sub(re.escape(cc.SOURCE_START) + r".*?" + re.escape(cc.SOURCE_END), "", out, flags=re.S)
        assert "Cite:" not in outside, "a citation carries the newsroom's titles and names: fence it"
        assert "The source's words" not in outside

    def test_json_is_valid_and_carries_the_terms(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{"data": {"articles": {"results": []},
                                                              "transcripts": {"results": []}}}]))
        cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring.{RQ}'), "--json"])
        captured = capsys.readouterr()
        report = json.loads(captured.out)
        assert report["results"][0]["status"] == "not found"
        assert "ai-train=no" in report["terms"] and "ai-train=no" in captured.err

    def test_no_quotations_exits_and_sends_nothing(self, env, tmp_path):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sent")))
        with pytest.raises(SystemExit) as e:
            cc.main([draft(tmp_path, "No quotations here at all.")])
        assert "Nothing was sent" in str(e.value)


class TestNextSteps:
    """HATEOAS: no dead end, a clear place to start, reasons,
    and commands that run as printed."""

    def test_dry_run_points_at_the_real_run(self, env, tmp_path, capsys):
        env.setattr(lna, "api_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sent")))
        path = draft(tmp_path, f'{LQ}We will finish the port by next spring,{RQ} said Jane Doe.')
        cc.main([path, "--dry-run"])
        out = capsys.readouterr().out
        assert "## Next steps" in out and "1. [high]" in out
        assert f"python3 scripts/cite_check.py {path}" in out
        assert "Related:" in out and "See also:" in out

    def test_a_quote_not_found_leads_with_a_search_for_its_words(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{"data": {"articles": {"results": []},
                                                              "transcripts": {"results": []}}}]))
        cc.main([draft(tmp_path, f"{LQ}We will finish the port by next spring.{RQ}")])
        out = capsys.readouterr().out
        first = out.split("## Next steps", 1)[1].split("2.")[0]
        assert "[high]" in first and "search 'We will finish the port by next spring'" in first

    def test_json_puts_next_steps_on_stderr(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{"data": {"articles": {"results": []},
                                                              "transcripts": {"results": []}}}]))
        cc.main([draft(tmp_path, f"{LQ}We will finish the port by next spring.{RQ}"), "--json"])
        cap = capsys.readouterr()
        json.loads(cap.out)
        line = [l for l in cap.err.splitlines() if l.startswith('{"next_steps"')][0]
        assert json.loads(line)["next_steps"][0]["priority"] == "high"


class TestNextStepsRunAndKeepTheRun:
    """From a code review of 0.2.0."""

    def test_a_path_that_needs_quoting_is_quoted(self, env, tmp_path, capsys):
        import shlex
        p = tmp_path / "my draft's copy.md"
        p.write_text(f'{LQ}We will finish the port by next spring,{RQ} said Jane Doe.', encoding="utf-8")
        cc.main([str(p), "--dry-run"])
        assert shlex.quote(str(p)) in capsys.readouterr().out

    def test_dry_run_rerun_keeps_the_users_flags(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring,{RQ} said Jane Doe.'),
                 "--dry-run", "--community", "other-news", "--min-words", "4"])
        steps = capsys.readouterr().out.split("## Next steps", 1)[1]
        first = steps.split("2.")[0]
        assert "--community other-news" in first and "--min-words 4" in first and "--dry-run" not in first

    def test_dry_run_with_no_quotes_points_at_shorter_ones(self, env, tmp_path, capsys):
        cc.main([draft(tmp_path, "No quotation marks here at all."), "--dry-run"])
        first = capsys.readouterr().out.split("## Next steps", 1)[1].split("2.")[0]
        assert "--min-words" in first and "--dry-run" in first

    def test_dry_run_json_is_json(self, env, tmp_path, capsys):
        cc.main([draft(tmp_path, f'{LQ}We will finish the port by next spring.{RQ}'), "--dry-run", "--json"])
        cap = capsys.readouterr()
        data = json.loads(cap.out)
        assert data["dry_run"] is True and data["quotations"][0]["would_send"]
        assert '{"next_steps"' in cap.err

    def test_no_quotes_under_json_still_prints_json(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        with pytest.raises(SystemExit):
            cc.main([draft(tmp_path, "No quotation marks."), "--json"])
        assert json.loads(capsys.readouterr().out)["results"] == []

    def test_out_step_is_dropped_when_out_was_given(self, env, tmp_path, capsys):
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{"data": {"articles": {"results": []},
                                                              "transcripts": {"results": []}}}]))
        cc.main([draft(tmp_path, f"{LQ}We will finish the port by next spring.{RQ}"), "--out",
                 str(tmp_path / "r.md")])
        assert "--out citations.md" not in capsys.readouterr().out

    @pytest.mark.parametrize("dry", [True, False])
    def test_every_command_parses_in_a_shell(self, env, tmp_path, capsys, dry):
        import shutil, subprocess
        env.setenv(lna.KEY_ENV, KEY)
        env.setattr(lna, "api_request", FakeSearch([{"data": {"articles": {"results": []},
                                                              "transcripts": {"results": []}}}]))
        argv = [draft(tmp_path, f"{LQ}We will finish the port by next spring.{RQ}"), "--json",
                "--community", "a b"] + (["--dry-run"] if dry else [])
        cc.main(argv)
        line = [l for l in capsys.readouterr().err.splitlines() if l.startswith('{"next_steps"')][0]
        bash = shutil.which("bash")
        for st in json.loads(line)["next_steps"]:
            if st["command"] and bash:
                cmd = re.sub(r"<[^>]+>", "X", st["command"])
                assert subprocess.run([bash, "-n", "-c", cmd]).returncode == 0, st["command"]

    def test_stdin_draft_becomes_a_placeholder(self):
        assert cc._draft_token("-").startswith("<")

    def test_this_suite_is_offline(self):
        import os
        assert os.environ.get("https_proxy") == "http://127.0.0.1:9" or os.environ.get("LOCAL_NEWS_API_LIVE")
