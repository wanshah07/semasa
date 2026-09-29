from fakestore import FakeStore

from semasa import studio_import

CAP = "Notifikasi kosmetik bukan kelulusan produk. NPRA menyemak dokumen selepas produk dipasarkan."
URLS = ["https://raw.githubusercontent.com/wanshah07/argus-cards/abc/studio/2026-10-03/R1003a-01.jpg"]


def _row(**kw):
    r = {"id": "11111111-1111-5111-8111-111111111111", "studio_id": "41oikyb71y", "stream": "regulab",
         "domain": "halal_my", "angle": None, "lang": "bm", "hook": "Hook",
         "text": {"bm": {"instagram": CAP, "facebook": CAP, "threads": CAP}}, "citation": "JAKIM", "slides": [],
         "date": "2026-10-03", "slot": "08:00", "status": "approved", "published": {},
         "approved_at": "2026-09-29T01:00:00Z",
         "media": {"id": "22222222-2222-5222-8222-222222222222", "urls": URLS, "alt": "kad", "studio_ids": ["c_1"]}}
    r.update(kw)
    return r


def _store(posts=()):
    return FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {}}}], semasa_posts=list(posts),
                     media_generations=[], semasa_log=[])


def test_an_approved_studio_post_arrives_approved_with_its_card():
    store = _store()
    rep = studio_import.apply(store, [_row()])
    post = store.tables["semasa_posts"][0]
    media = store.tables["media_generations"][0]
    assert post["status"] == "approved" and post["media_ids"] == [media["id"]] and post["hard_flags"] == 0
    assert media["status"] == "done" and media["mode"] == "slides" and media["meta"]["slide_urls"] == URLS
    assert media["generated_media_url"] == URLS[0] and rep["written"] and not rep["hard"]


def test_running_it_twice_changes_nothing_and_a_27_sep_draft_is_brought_up_to_date():
    old = {"id": _row()["id"], "status": "draft", "stream": "regulab", "date": "2026-10-03", "slot": "08:00"}
    store = _store([old])
    studio_import.apply(store, [_row()])
    studio_import.apply(store, [_row()])
    assert len(store.tables["semasa_posts"]) == 1 and store.tables["semasa_posts"][0]["status"] == "approved"
    assert len(store.tables["media_generations"]) == 1


def test_semasas_own_sent_post_is_never_overwritten():
    sent = {"id": _row()["id"], "status": "scheduled", "stream": "regulab", "date": "2026-10-03", "slot": "08:00"}
    store = _store([sent])
    rep = studio_import.apply(store, [_row()])
    assert rep["kept_semasa"] == ["41oikyb71y"] and store.tables["semasa_posts"][0]["status"] == "scheduled"


def test_a_slot_clash_with_a_semasa_post_is_reported_not_resolved():
    mine = {"id": "x", "status": "draft", "stream": "regulab", "date": "2026-10-03", "slot": "08:00", "hook": "h"}
    rep = studio_import.apply(_store([mine]), [_row()])
    assert len(rep["clashes"]) == 1


def test_dry_run_writes_nothing():
    store = _store()
    rep = studio_import.apply(store, [_row()], dry=True)
    assert rep["written"] and store.tables["semasa_posts"] == [] and store.tables["media_generations"] == []


def test_an_approved_post_without_a_picture_is_named_as_blocked():
    rep = studio_import.apply(_store(), [_row(media=None)])
    assert rep["hard"] and "instagram needs an image" in rep["hard"][0]
