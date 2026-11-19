"""
Spec checks for the skills that ship a copy of the Local News API client.

`local-news-api` carries its own, deeper suite. The skills built on it (meeting-prep,
cite-check) share these: the agentskills.io frontmatter rules, the catalog limits, the
registry bundle, the read-only contract, the declared environment, the User-Agent, and
the one that is new with them: the client copy each ships must be byte-identical to the
canonical one, or a fix to the client reaches one skill and not another.

    python3 -m pytest tests/test_skill_spec.py -q
"""
import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "skills" / "local-news-api" / "scripts" / "local_news_api.py"
# Each skill that ships the client, with its own script.
CONSUMERS = {"meeting-prep": "meeting_prep.py", "cite-check": "cite_check.py"}
SKILLS = sorted(CONSUMERS)


def skill_dir(name):
    return ROOT / "skills" / name


def frontmatter(name):
    """SKILL.md's YAML frontmatter, parsed without a YAML dependency. Handles the shapes
    these files use: `key: value`, `key: >-` folded blocks, `key:` with an indented
    map, and inside it a JSON-style flow mapping that may span lines."""
    text = (skill_dir(name) / "SKILL.md").read_text()
    assert text.startswith("---\n"), f"{name}/SKILL.md must open with YAML frontmatter"
    body = text.split("---\n", 2)[1]
    out, key, folded, mapping = {}, None, None, None
    flow_key, flow = None, None

    def balanced(s):
        return s.count("{") + s.count("[") == s.count("}") + s.count("]")

    for raw in body.splitlines():
        if flow is not None:
            flow.append(raw.strip())
            if balanced(" ".join(flow)):
                mapping[flow_key] = json.loads(" ".join(flow))
                flow_key, flow = None, None
            continue
        if not raw.strip():
            continue
        indented = raw.startswith("  ")
        if indented and folded is not None:
            folded.append(raw.strip())
            continue
        if indented and mapping is not None:
            k, _, v = raw.strip().partition(":")
            v = v.strip()
            if v.startswith("{"):
                if balanced(v):
                    mapping[k.strip()] = json.loads(v)
                else:
                    flow_key, flow = k.strip(), [v]
                continue
            mapping[k.strip()] = v.strip('"').strip("'")
            continue
        if key and folded is not None:
            out[key] = " ".join(folded)
        key, folded, mapping = None, None, None
        k, _, v = raw.partition(":")
        k, v = k.strip(), v.strip()
        if v in (">-", ">", "|"):
            key, folded = k, []
        elif v == "":
            out[k] = mapping = {}
        else:
            out[k] = v.strip('"').strip("'")
    if key and folded is not None:
        out[key] = " ".join(folded)
    return out


def script_src(name):
    return (skill_dir(name) / "scripts" / CONSUMERS[name]).read_text()


def env_reads(src, module=None):
    names = set()
    for m in re.finditer(r'os\.(?:environ\.get|getenv)\(\s*(?:"([A-Z0-9_]+)"|([A-Za-z_][A-Za-z0-9_]*))', src):
        literal, ident = m.groups()
        if literal:
            names.add(literal)
        else:
            consts = dict(re.findall(r'^([A-Z_]+) = "([A-Z0-9_]+)"', src, re.M))
            assert ident in consts, f"cannot resolve env read os.environ.get({ident})"
            names.add(consts[ident])
    assert not re.search(r"os\.environ\[", src), "subscripted env reads are not covered here"
    return names


class TestTheClientCopy:
    @pytest.mark.parametrize("name", SKILLS)
    def test_the_shipped_client_is_byte_identical_to_the_canonical_one(self, name):
        """A copy that drifts is a fix that reached one skill and not another. Run
        scripts/sync-shared-client.sh after any change to the canonical client."""
        copy = skill_dir(name) / "scripts" / "local_news_api.py"
        assert copy.exists(), f"{name} must ship scripts/local_news_api.py"
        assert copy.read_bytes() == CANONICAL.read_bytes(), (
            f"{name}/scripts/local_news_api.py differs from the canonical client: "
            "run scripts/sync-shared-client.sh")

    def test_the_sync_script_names_every_consumer(self):
        sync = (ROOT / "scripts" / "sync-shared-client.sh").read_text()
        for name in SKILLS:
            assert name in sync, f"sync-shared-client.sh does not copy into {name}"


class TestSpec:
    @pytest.mark.parametrize("name", SKILLS)
    def test_name_matches_the_folder(self, name):
        fm = frontmatter(name)
        assert fm["name"] == name
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm["name"])

    @pytest.mark.parametrize("name", SKILLS)
    def test_description_fits(self, name):
        d = frontmatter(name)["description"]
        assert 0 < len(d) < 1024, f"description is {len(d)} characters"

    @pytest.mark.parametrize("name", SKILLS)
    def test_skill_md_stays_small(self, name):
        lines = (skill_dir(name) / "SKILL.md").read_text().count("\n")
        assert lines < 500, f"{name}/SKILL.md is {lines} lines"

    @pytest.mark.parametrize("name", SKILLS)
    def test_links_resolve_and_stay_inside_the_folder(self, name):
        sd = skill_dir(name)
        for target in re.findall(r"\]\(([^)#\s]+)", (sd / "SKILL.md").read_text()):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (sd / target).resolve()
            assert resolved.exists(), f"{name}/SKILL.md links to a missing {target}"
            assert sd.resolve() in resolved.parents, f"{target} leaves the skill folder"

    @pytest.mark.parametrize("name", SKILLS)
    def test_no_template_variables(self, name):
        text = (skill_dir(name) / "SKILL.md").read_text()
        assert "{{" not in text and "${" not in text

    @pytest.mark.parametrize("name", SKILLS)
    def test_no_em_or_en_dashes_in_prose_or_code(self, name):
        dashes = re.compile("[\u2013\u2014]")
        assert dashes.search("x \u2014 y"), "the pattern must be able to fire"
        for path in [skill_dir(name) / "SKILL.md", skill_dir(name) / "scripts" / CONSUMERS[name],
                     skill_dir(name) / "agents" / "openai.yaml"]:
            hits = [i + 1 for i, line in enumerate(path.read_text().splitlines()) if dashes.search(line)]
            assert not hits, f"{path.name} has an em or en dash on lines {hits}"


class TestRegistry:
    @pytest.mark.parametrize("name", SKILLS)
    def test_declared_env_matches_what_the_code_reads(self, name):
        oc = frontmatter(name)["metadata"]["openclaw"]
        declared = {e["name"] for e in oc["envVars"]}
        read = env_reads(CANONICAL.read_text()) | env_reads(script_src(name))
        assert read - declared == set(), f"read but not declared: {sorted(read - declared)}"
        assert declared - read == set(), f"declared but never read: {sorted(declared - read)}"
        assert all(e.get("required") is False for e in oc["envVars"])
        assert all(str(e.get("description", "")).strip() for e in oc["envVars"])

    @pytest.mark.parametrize("name", SKILLS)
    def test_user_agent_is_name_and_version(self, name):
        fm = frontmatter(name)
        src = script_src(name)
        assert f'NAME = "{fm["name"]}"' in src
        assert f'VERSION = "{fm["metadata"]["version"]}"' in src
        assert "lna.UA = UA" in src, "the shared client must send this skill's User-Agent"

    @pytest.mark.parametrize("name", SKILLS)
    def test_catalog_limits_and_read_only(self, name):
        text = (skill_dir(name) / "agents" / "openai.yaml").read_text()
        display = re.search(r'display_name: "([^"]+)"', text).group(1)
        short = " ".join(text.split("short_description: >-", 1)[1].split())
        assert len(display) <= 120 and len(short) <= 300
        assert "Read-only" in short and "Alaska News" in short

    @pytest.mark.parametrize("name", SKILLS)
    def test_tests_and_keys_stay_out_of_the_bundle(self, name):
        ignored = {ln.strip() for ln in (skill_dir(name) / ".clawhubignore").read_text().splitlines()
                   if ln.strip() and not ln.startswith("#")}
        test_file = f"scripts/test_{CONSUMERS[name]}"
        assert test_file in ignored
        assert {".env", ".env.local"} <= ignored
        assert f"test_{CONSUMERS[name]}" not in (skill_dir(name) / "SKILL.md").read_text()


class TestReadOnly:
    @pytest.mark.parametrize("name", SKILLS)
    def test_only_get_requests(self, name):
        """These skills read. Not even the client's one read-only POST is used."""
        src = script_src(name)
        verbs = set(re.findall(r'api_request\(\s*"([A-Z]+)"', src))
        assert verbs == {"GET"}, f"{name} uses {sorted(verbs)}"
        for verb in ('"PATCH"', '"PUT"', '"DELETE"', '"POST"'):
            assert verb not in src

    @pytest.mark.parametrize("name", SKILLS)
    def test_the_one_local_write_is_out_and_is_declared(self, name):
        """Writes to disk only under --out, and SKILL.md's table says so."""
        tree = ast.parse(script_src(name))
        writes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr in {"write_text", "write_bytes", "mkdir", "unlink", "touch"}]
        assert len(writes) == 1, f"{name} has {len(writes)} disk writes, expected only --out"
        src = script_src(name)
        line = src.splitlines()[writes[0].lineno - 1]
        assert "args.out" in line, "the write must be the --out file"
        row = next(ln for ln in (skill_dir(name) / "SKILL.md").read_text().splitlines()
                   if ln.startswith("| **Local files** |"))
        assert "--out" in row

    @pytest.mark.parametrize("name", SKILLS)
    def test_the_read_only_direction_is_stated(self, name):
        text = (skill_dir(name) / "SKILL.md").read_text()
        assert "READ ONLY" in text and "only consumes" in text
