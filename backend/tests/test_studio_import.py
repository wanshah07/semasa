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


def test_the_post_is_written_before_its_picture_because_the_picture_points_at_it():
    store = _store()
    order = []
    real = store.table

    def table(name):
        q = real(name)
        up = q.upsert

        def upsert(*a, **k):
            order.append(name)
            return up(*a, **k)
        q.upsert = upsert
        return q
    store.table = table
    studio_import.apply(store, [_row()])
    assert order == ["semasa_posts", "media_generations"]


# --- Studio's open ideas (Wan, 3 Oct 2026): into the Regulatory feed, never into semasa_ideas, never over a live post ---

def _idea(**kw):
    i = {"studio_id": "i_eusgvahranbmhca0929",
         "title": "EU Safety Gate: minyak wangi Scent of VAHRAN mengandungi BMHCA (SR/02687/26)",
         "ref_no": "SR/02687/26", "match": ["vahran"], "source": "EU Safety Gate", "kind": "Safety alert", "country": "EU",
         "url": "https://ec.europa.eu/safety-gate-alerts/screen/home#SR/02687/26", "tier": "I", "markets": ["EU (Hungary)"],
         "at": "2026-09-30T14:17:07.000Z", "domain": "kosmetik", "evidence": "",
         "note": "Amaran Hungary SR/02687/26: BMHCA dilarang. Sudut: BMHCA berulang selepas kes LACOSTE. "
                 "[SAHKAN: baris 29/09/2026 hanya bawa satu pautan, bukan untuk penemuan ini]"}
    i.update(kw)
    return i


def _wstore(posts=(), watch=()):
    return FakeStore(semasa_posts=list(posts), semasa_watch=list(watch), semasa_ideas=[], semasa_log=[])


def test_an_open_idea_becomes_a_regulatory_row_ready_for_wans_click_and_nothing_else():
    store = _wstore()
    rep = studio_import.apply_ideas(store, [_idea()])
    row = store.tables["semasa_watch"][0]
    assert rep["written"] and row["section"] == "regulatory" and row["status"] == "ready" and row["pasted"] is False
    # no idea (it would wake the worker), no post
    assert store.tables["semasa_ideas"] == [] and store.tables["semasa_posts"] == []
    assert row["summary"].startswith("Amaran Hungary") and row["why"] == "BMHCA berulang selepas kes LACOSTE."
    # a writer would copy the marker into a caption
    assert "SAHKAN" not in (row["summary"] or "") + (row["why"] or "")
    assert "SAHKAN" in row["raw"]["caveat"] and row["raw"]["ref"] == "SR/02687/26" and row["lang"] == "ms"


def test_an_idea_already_in_a_live_post_is_left_alone_so_nothing_in_buffer_is_repeated():
    posted = {"id": "p1", "status": "scheduled", "hook": "x", "citation": "EU Safety Gate SR/02687/26",
              "text": {"bm": {"facebook": "-"}}}
    by_name = {"id": "p2", "status": "posted", "hook": "x", "citation": "",
               "text": {"bm": {"facebook": "Scent of VAHRAN ditarik balik"}}}
    for p in (posted, by_name):
        store = _wstore([p])
        rep = studio_import.apply_ideas(store, [_idea()])
        assert rep["already_posted"] and not rep["written"] and store.tables["semasa_watch"] == []
    # a draft is not a post in Buffer
    draft = {"id": "p3", "status": "draft", "hook": "x", "citation": "SR/02687/26", "text": {}}
    assert studio_import.apply_ideas(_wstore([draft]), [_idea()])["written"]


def test_running_it_twice_and_a_link_already_in_the_feed_change_nothing_and_dry_writes_nothing():
    store = _wstore()
    studio_import.apply_ideas(store, [_idea()], dry=True)
    assert store.tables["semasa_watch"] == []
    studio_import.apply_ideas(store, [_idea()])
    rep = studio_import.apply_ideas(store, [_idea()])
    assert len(store.tables["semasa_watch"]) == 1 and rep["already_there"] == ["i_eusgvahranbmhca0929"]


def test_an_idea_without_a_link_of_its_own_says_so_and_a_real_link_is_kept():
    bare = studio_import.watch_row(_idea())
    assert "did not record a link" in bare["raw"]["caveat"] or "SAHKAN" in bare["raw"]["caveat"]
    real = studio_import.watch_row(_idea(evidence="https://docs.wto.org/x.pdf", note="Draf. Sudut: jiran ASEAN."))
    assert real["raw"]["evidence"] == "https://docs.wto.org/x.pdf" and "caveat" not in real["raw"]
