"""My designs: a saved look with no words, carried on a job as a snapshot, chosen by the idea or by the default."""
from semasa import ideas, my_designs

ERA = {"id": "ab12cd", "name": "Biru", "look": "era", "cover": "e_hook", "middle": "e_check", "single": "e_stat",
       "accent": "#0a7c6e", "paper": "#f3efe6", "bg": "lib:g_makmal02", "scrim": "none", "junk": "x", "eyebrow": "Kosmetik"}
GRID = {"id": "zz99yy", "name": "Krim", "look": "grid", "closing": "g_title"}
BAD = {"id": "nope1234", "look": "classic"}


class _Q:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_):
        return self

    def in_(self, col, keys):
        self.rows = [r for r in self.rows if r[col] in keys]
        return self

    def execute(self):
        return type("R", (), {"data": self.rows})


class _Store:
    def __init__(self, designs=None, default=None, boom=False):
        self.rows = []
        if designs is not None:
            self.rows.append({"key": "designs", "value": designs})
        if default is not None:
            self.rows.append({"key": "default_design", "value": {"id": default}})
        self.boom = boom

    def table(self, name):
        assert name == "semasa_settings"
        if self.boom:
            raise RuntimeError("down")
        return _Q(list(self.rows))


def test_pack_keeps_only_known_string_keys_of_a_studio_family():
    got = my_designs.pack(ERA)
    assert got["look"] == "era" and got["cover"] == "e_hook" and got["accent"] == "#0a7c6e"
    assert "junk" not in got and "id" not in got
    assert my_designs.pack(BAD) is None and my_designs.pack(None) is None and my_designs.pack("x") is None


def test_a_design_is_found_by_its_token_and_a_plain_look_is_left_alone():
    ds = [ERA, GRID, BAD]
    assert my_designs.token("d:ab12cd") == "ab12cd" and my_designs.token("grid") is None and my_designs.token("d:x") is None
    look, d = my_designs.choose(ds, "", "d:zz99yy")
    assert look == "grid" and d["closing"] == "g_title"
    assert my_designs.choose(ds, "", "photo") == ("photo", None)
    assert my_designs.choose(ds, "", "d:gone1234") == ("classic", None)          # a deleted design: Semasa's own drawing
    assert my_designs.choose(ds, "", "d:nope1234") == ("classic", None)          # a design with no usable family


def test_the_default_design_applies_only_when_the_idea_chose_no_look():
    ds = [ERA, GRID]
    assert my_designs.choose(ds, "ab12cd", "")[0] == "era"
    assert my_designs.choose(ds, "ab12cd", "classic") == ("classic", None)   # Semasa's own drawing, chosen on purpose, stands
    assert my_designs.choose(ds, "ab12cd", "grid") == ("grid", None)           # an explicit look beats the default
    assert my_designs.choose(ds, "ab12cd", "d:zz99yy")[0] == "grid"
    assert my_designs.choose(ds, "missing1", "classic") == ("classic", None)


def test_settings_are_read_and_a_missing_or_failed_read_is_just_off():
    assert my_designs.load(_Store([ERA], "ab12cd")) == ([ERA], "ab12cd")
    assert my_designs.load(_Store()) == ([], "")                               # supabase/027 not run yet
    assert my_designs.load(_Store(boom=True)) == ([], "")
    assert my_designs.load(_Store("garbage", None)) == ([], "")


def test_for_idea_reads_the_look_from_the_idea_brief():
    store = _Store([ERA, GRID], "ab12cd")
    assert my_designs.for_idea(store, {"brief": {}})[0] == "era"                       # nothing chosen: the default
    assert my_designs.for_idea(store, {"brief": {"look": "classic"}}) == ("classic", None)   # chosen: it stands
    assert my_designs.for_idea(store, {"brief": {"look": "d:zz99yy"}})[0] == "grid"
    assert my_designs.for_idea(store, {"brief": {"look": "photo"}}) == ("photo", None)
    assert ideas.look_of({"brief": {"look": "d:zz99yy"}}) == "d:zz99yy"
    assert ideas.look_of({"brief": {"look": "d:???"}}) == "classic"


def test_the_jobs_carry_the_snapshot_the_look_and_the_designs_background():
    idea, post = {"id": "i1", "created_by": "u", "brief": {}}, {"stream": "regulab", "slides": [{"title": "x"}], "citation": ""}
    chosen = my_designs.choose([ERA], "", "d:ab12cd")
    job = ideas.slide_job(idea, post, "p1", "none", chosen=chosen)
    m = job["meta"]
    assert m["look"] == "era" and m["fit"] is True and m["bg"] == "lib:g_makmal02" and m["design_pack"]["cover"] == "e_hook"
    own = ideas.slide_job(idea, post, "p1", "post_image", chosen=chosen)["meta"]
    assert own["bg"] == "post_image"                                                   # the post's own picture beats the design's
    poster = ideas.poster_job(idea, post, "p1", [{"title": "x"}], "none", chosen=chosen)["meta"]
    assert poster["design"] == "poster" and poster["design_pack"]["single"] == "e_stat" and poster["look"] == "era"
    plain = ideas.slide_job(idea, post, "p1", "none")["meta"]
    assert "design_pack" not in plain and plain["look"] == "classic"


def test_a_design_made_from_a_reference_carries_its_layouts_within_bounds():
    head = {"type": "text", "role": "headline", "x": 0, "y": 0, "w": 1, "h": 0.1}
    layout = {"background": {"color": "#fff"}, "elements": [head]}
    layouts = {"main": layout, "cover": layout, "bogus": layout, "closing": "x", "single": {"elements": 3}}
    got = my_designs.pack({"look": "grid", "layouts": layouts})
    assert set(got["layouts"]) == {"main", "cover"}                         # only known places holding a layout
    huge = {"look": "grid", "layouts": {"main": {"elements": [{"type": "text", "text": "x" * 400}] * 400}}}
    assert "layouts" not in my_designs.pack(huge)                           # a layout beyond the size cap is not carried
    assert "layouts" not in my_designs.pack({"look": "grid", "layouts": "nope"})


def test_a_reference_design_does_not_get_a_default_ground_it_never_asked_for():
    idea = {"id": "i1", "created_by": "u", "brief": {}}
    post = {"stream": "regulab", "domain": "kosmetik", "slides": [{"title": "x"}]}
    layout = {"elements": [{"type": "text", "role": "headline", "x": 0, "y": 0, "w": 1, "h": 0.1}]}
    ref = my_designs.choose([{"id": "ref1234", "look": "grid", "layouts": {"main": layout}}], "", "d:ref1234")
    assert ideas.slide_job(idea, post, "p1", "none", chosen=ref)["meta"]["bg"] == "none"
    plain = ideas.slide_job(idea, post, "p1", "none", chosen=("grid", None))["meta"]["bg"]
    assert plain != "none"                                                  # a Studio look still gets the domain's ground


ART_UID = "0b9f1a52-6c1e-4f6e-9c1a-3a1d2b7c9e10"


def test_the_reference_picture_is_carried_as_a_path_a_size_and_patches_that_have_a_colour():
    art = {"path": f"{ART_UID}/ref.jpg", "w": 800, "h": 1000, "patches": [
        {"x": 0.1, "y": 0.1, "w": 0.4, "h": 0.1, "kind": "text", "fill": "#e6e6f0"},
        {"x": 0, "y": 0.5, "w": 1, "h": 0.2, "gradient": {"from": "#fff", "to": "#000"}},
        {"x": 0, "y": 0, "w": 1, "h": 1},                                   # no colour: dropped
        {"x": "a", "y": 0, "w": 1, "h": 1, "fill": "#000"}]}                 # not a number: dropped
    got = my_designs.pack({"look": "grid", "refart": art})["refart"]
    assert got["path"] == art["path"] and (got["w"], got["h"]) == (800, 1000) and len(got["patches"]) == 2
    for bad in ({**art, "path": "../../etc/passwd"}, {**art, "path": "ref.jpg"}, {**art, "w": 10}, {**art, "h": "x"},
                "nope", None):
        assert "refart" not in my_designs.pack({"look": "grid", "refart": bad})   # malformed: dropped
