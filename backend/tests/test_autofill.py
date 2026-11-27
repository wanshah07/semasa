"""Filling empty slots: off unless switched on, rota-true, never two ideas for one slot, drafts only."""

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import autofill

NOW = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)            # Thu 24 Sep, 10:00 MYT
BRAND = {"regulab": {"slots": ["08:00", "13:00"], "schedule": {"5": ["kosmetik", "sains_kosmetik"], "6": [],
                                                                "0": ["halal_my", "fatwa"]}},
         "linkedin": {"slots": ["06:00"], "days": [1, 3, 5]}}


def _store(watch, ideas=(), posts=()):
    return FakeStore(semasa_watch=list(watch), semasa_ideas=list(ideas), semasa_posts=list(posts), semasa_log=[])


def _w(i, domain, section="regulatory"):
    return {"id": f"w{i}", "section": section, "source": "NPRA", "title": f"Notis {i}", "url": f"https://npra.gov.my/{i}",
            "summary": "s", "domain": domain, "relevant": True, "dismissed": False, "created_at": "2026-09-23T00:00:00+00:00"}


def test_off_by_default_writes_nothing():
    store = _store([_w(1, "kosmetik")])
    assert autofill.run(store, {"brand": BRAND}, NOW).startswith("Autofill: off")
    assert autofill.run(store, {"brand": BRAND, "autofill": {"enabled": "yes"}}, NOW).startswith("Autofill: off")
    assert store.tables["semasa_ideas"] == []


def test_fills_rota_true_positions_from_tomorrow_and_leaves_the_rest_as_gaps():
    store = _store([_w(1, "halal_my"), _w(2, "kosmetik"), _w(3, "farmaseutikal")],
                   posts=[{"id": "p", "stream": "regulab", "status": "draft", "date": "2026-09-25", "slot": "08:00"}])
    out = autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 3, "per_run": 5,
                                                             "streams": ["regulab"]}}, NOW)
    got = sorted((i["brief"]["position"]["date"], i["brief"]["position"]["slot"], i["domain"], i["source_url"][-1])
                 for i in store.tables["semasa_ideas"])
    # Fri 25: 08:00 taken, 13:00 → the kosmetik item; Sat: no posting; Sun 27: halal item at 08:00, 13:00 has nothing
    assert got == [("2026-09-25", "13:00", "kosmetik", "2"), ("2026-09-27", "08:00", "halal_my", "1")]
    assert "1 gap(s) had no fitting item" in out
    assert all(i["status"] == "new" and i["brief"]["auto"] is True for i in store.tables["semasa_ideas"])


def test_never_two_ideas_for_one_slot_nor_one_item_twice():
    waiting = {"id": "i0", "stream": "regulab", "status": "new", "source_url": "https://npra.gov.my/2",
               "brief": {"position": {"date": "2026-09-25", "slot": "08:00"}}}
    store = _store([_w(2, "kosmetik"), _w(4, "kosmetik")], ideas=[waiting])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 5,
                                                       "streams": ["regulab"]}}, NOW)
    new = [i for i in store.tables["semasa_ideas"] if i["id"] != "i0"]
    assert [(i["brief"]["position"]["slot"], i["source_url"][-1]) for i in new] == [("13:00", "4")]


def test_per_run_cap_and_linkedin_days():
    store = _store([_w(i, "kosmetik", "publication") for i in range(6)])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 7, "per_run": 2,
                                                       "streams": ["linkedin"]}}, NOW)
    ideas = store.tables["semasa_ideas"]
    assert len(ideas) == 2 and all(i["angle"] == "F" and i["domain"] is None for i in ideas)
    assert [i["brief"]["position"]["date"] for i in ideas] == ["2026-09-25", "2026-09-28"]   # Fri, then Mon


def test_a_case_study_fits_any_posting_day():
    store = _store([_w(1, "kajian_kes")])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 1,
                                                       "streams": ["regulab"]}}, NOW)
    assert store.tables["semasa_ideas"][0]["domain"] == "kajian_kes"


def test_an_autofilled_idea_carries_no_note_so_the_published_guard_still_holds():
    store = _store([_w(1, "kosmetik")])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 1,
                                                       "streams": ["regulab"]}}, NOW)
    assert store.tables["semasa_ideas"][0]["note"] == ""


def test_autofill_opens_by_itself_at_enabled_from():
    s = {"autofill": {"enabled": False, "enabled_from": "2026-10-02T12:00:00Z"}}
    assert autofill.config(s, datetime(2026, 10, 2, 11, 0, tzinfo=UTC))["enabled"] is False
    assert autofill.config(s, datetime(2026, 10, 2, 12, 0, tzinfo=UTC))["enabled"] is True


def test_a_linkedin_slot_set_to_video_is_a_single_card_never_a_film():
    """Wan, 11 Nov 2026: "for linkedn, no need to do motion, only carousel or single card"."""
    brand = {"linkedin": {"slot_formats": {"06:00": "carousel", "19:00": "video"}},
             "regulab": {"slot_formats": {"08:00": "video"}}}
    assert autofill.slot_format(brand, "linkedin", "19:00") == "single"
    assert autofill.slot_format(brand, "linkedin", "06:00") == "carousel"
    assert autofill.slot_format(brand, "regulab", "08:00") == "video", "ws.regulab still has its film slots"


def test_a_linkedin_gap_written_by_autofill_is_an_idea_never_a_motion_film():
    brand = {**BRAND, "linkedin": {"slots": ["06:00"], "days": [0, 1, 2, 3, 4, 5, 6], "slot_formats": {"06:00": "video"}}}
    store = FakeStore(semasa_watch=[_w(1, "kosmetik")], semasa_ideas=[], semasa_posts=[], semasa_log=[], semasa_motions=[])
    cfg = {"enabled": True, "days_ahead": 3, "per_run": 4, "streams": ["linkedin"]}
    autofill.run(store, {"brand": brand, "autofill": cfg}, NOW)
    assert not [m for m in store.tables["semasa_motions"] if m.get("stream") == "linkedin"], "no LinkedIn film is queued"
    assert [i for i in store.tables["semasa_ideas"] if i.get("stream") == "linkedin"], "the slot gets an idea for a post instead"


# --- LinkedIn from official sources, and posters (Wan, 20 Nov 2026) ---------------------------------------

def test_linkedin_takes_only_official_sections_never_a_headline_or_a_social_post():
    for section in ("regulatory", "publication", "website", "folder"):
        assert autofill.fits({"section": section}, "linkedin", None), section
    for section in ("news", "linkedin", "expert", "reddit", "youtube", "threads", "instagram", "facebook", ""):
        assert not autofill.fits({"section": section}, "linkedin", None), section
    assert autofill.fits({"section": "news", "domain": "halal_my"}, "regulab", ["halal_my"])      # ws.regulab is unchanged


def test_a_poster_slot_makes_a_poster_idea_not_a_carousel_or_a_single_card():
    brand = {"linkedin": {"slots": ["06:00", "19:00"], "slot_formats": {"06:00": "carousel", "19:00": "poster"}}}
    assert autofill.slot_format(brand, "linkedin", "19:00") == "poster"
    assert autofill.slot_format(brand, "linkedin", "06:00") == "carousel"
    from semasa import ideas
    assert ideas.format_of({"brief": {"format": "poster"}}) == "poster"


def test_linkedin_takes_an_updated_circular_before_an_existing_guideline_before_research():
    # Wan, 23 Nov 2026: "updated circular/guideline > existing guideline > research"
    def row(i, section, title, summary="s"):
        return {**_w(i, "kosmetik", section), "title": title, "summary": summary,
                "created_at": f"2026-09-23T0{9 - i}:00:00+00:00"}              # the research paper is the newest
    store = _store([row(1, "publication", "A new trial of a cream"),
                    row(2, "website", "Garis panduan sedia ada"),
                    row(3, "regulatory", "Kenyataan tentang kilang"),
                    row(4, "folder", "Nota rujukan"),
                    row(5, "regulatory", "NPRA updates the cosmetic guideline", "Pindaan Garis Panduan Notifikasi")])
    brand = {"linkedin": {"slots": ["06:00", "11:00", "19:00"], "days": [0, 1, 2, 3, 4, 5, 6]}}
    cfg = {"enabled": True, "days_ahead": 2, "per_run": 5, "streams": ["linkedin"]}
    autofill.run(store, {"brand": brand, "autofill": cfg}, NOW)
    got = [i["source_url"][-1] for i in sorted(store.tables["semasa_ideas"], key=lambda i: (
        i["brief"]["position"]["date"], i["brief"]["position"]["slot"]))]
    assert got == ["5", "3", "2", "4", "1"], got
    assert [autofill.linkedin_tier(x) for x in (row(5, "regulatory", "Updated guideline"), row(3, "regulatory", "Kenyataan"),
                                                row(2, "website", "x"), row(4, "folder", "x"),
                                                row(1, "publication", "x"))] == [0, 1, 2, 3, 4]


def test_linkedin_prefers_halal_then_cosmetic_then_pharma_then_research_whatever_the_tier():
    # Wan, 23 Nov 2026: "for linkedn, add more about halal>cosmetic>pharma>research"
    def row(i, domain, section, title="Kenyataan", created="2026-09-20T00:00:00+00:00"):
        return {**_w(i, domain, section), "title": title, "summary": "s", "created_at": created}
    halal_site = row(1, "halal_my", "website", "Garis panduan sedia ada")           # tier 2, but halal
    cosmetic_new = row(2, "kosmetik", "regulatory", "Updated guideline", "2026-09-23T00:00:00+00:00")   # tier 0
    pharma = row(3, "farmaseutikal", "regulatory", "Updated circular", "2026-09-23T00:00:00+00:00")
    paper = row(4, "sains_kosmetik", "publication", "A trial", "2026-09-23T00:00:00+00:00")
    food = row(5, "makanan", "regulatory", "Updated circular", "2026-09-23T00:00:00+00:00")
    assert [autofill.linkedin_subject(x) for x in (halal_site, cosmetic_new, pharma, paper, food)] == [0, 1, 2, 3, 4]
    pool = [food, paper, pharma, cosmetic_new, halal_site]
    order = []
    while pool:
        got = autofill.pick(autofill.rank_candidates(pool), "linkedin", None, "2026-09-25")
        order.append(got["id"])
        pool.remove(got)
    assert order == [halal_site["id"], cosmetic_new["id"], pharma["id"], paper["id"], food["id"]], order
    assert [autofill.linkedin_angle(x) for x in (halal_site, cosmetic_new, paper)] == ["B", "A", "F"]


def test_ws_regulab_keeps_its_own_order_when_linkedin_has_one():
    paper, notice = _w(1, "kosmetik", "publication"), _w(2, "kosmetik", "regulatory")
    ranked = autofill.rank_candidates([paper, notice])
    assert autofill.pick(ranked, "regulab", ["kosmetik"], "2026-09-25") is notice


def test_inside_a_linkedin_tier_the_newest_item_wins_even_when_an_older_one_is_an_announcement():
    # Codex review on #327: an "Updated guideline" notice and a recall are both tier 0 for LinkedIn, and the shared ranking
    # puts the recall first whatever its date
    older = {**_w(1, "kosmetik"), "title": "Recall of a cream", "summary": "s", "created_at": "2026-09-20T00:00:00+00:00"}
    newer = {**_w(2, "kosmetik"), "title": "Updated guideline on labels", "summary": "s",
             "created_at": "2026-09-23T00:00:00+00:00"}
    assert autofill.linkedin_tier(older) == autofill.linkedin_tier(newer) == 0
    ranked = autofill.rank_candidates([older, newer])
    assert ranked[0] is older, "the shared order puts the announcement first"
    assert autofill.pick(ranked, "linkedin", None, "2026-09-25") is newer


def test_a_slot_with_no_format_is_a_carousel_and_only_a_single_slot_is_one_card():
    got = [autofill.auto_format(f) for f in ("", "carousel", "single", "poster", "video")]
    assert got == ["carousel", "carousel", "poster", "poster", "video"]


# ---- the floor of waiting drafts (Wan, 25 Nov 2026) -------------------------------------------------------------------------
def _full_friday():
    """Approved posts on every ws.regulab and LinkedIn position of Fri 25 Sep: the gap pass (days_ahead 1) has nothing to do."""
    return [{"id": f"f{n}", "stream": s, "status": "approved", "date": "2026-09-25", "slot": slot}
            for n, (s, slot) in enumerate([("regulab", "08:00"), ("regulab", "13:00"), ("linkedin", "06:00")])]


def _floor_settings(**over):
    return {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 5, "streams": ["regulab"], **over}}


def test_floor_config_defaults_and_clamps():
    assert autofill.config({"autofill": {"enabled": True}})["min_drafts"] == 2
    assert autofill.config({"autofill": {"enabled": True}})["floor_days"] == 14
    cfg = autofill.config({"autofill": {"enabled": True, "min_drafts": 0, "days_ahead": 5, "floor_days": 2}})
    assert cfg["min_drafts"] == 0 and cfg["floor_days"] == 5            # off; never fewer days than the gap pass looks
    assert autofill.config({"autofill": {"enabled": True, "min_drafts": 99, "floor_days": 99}})["min_drafts"] == 10
    assert autofill.config({"autofill": {"enabled": True, "min_drafts": 99, "floor_days": 99}})["floor_days"] == 30
    assert autofill.config({"autofill": {"enabled": True, "min_drafts": "x"}})["min_drafts"] == 2


def test_floor_writes_two_ideas_for_positions_beyond_the_gap_window():
    store = _store([_w(1, "halal_my"), _w(2, "fatwa"), _w(3, "halal_my")], posts=_full_friday())
    out = autofill.run(store, _floor_settings(), NOW)
    got = sorted((i["brief"]["position"]["date"], i["brief"]["position"]["slot"]) for i in store.tables["semasa_ideas"])
    assert got == [("2026-09-27", "08:00"), ("2026-09-27", "13:00")]        # the next free positions, rota-true (Sunday: halal)
    assert "floor: 2 idea(s) so 2 drafts are waiting" in out
    assert all(i["status"] == "new" and i["brief"]["auto"] is True for i in store.tables["semasa_ideas"])
    assert [p["status"] for p in store.tables["semasa_posts"]] == ["approved"] * 3      # nothing approved, nothing scheduled


def test_floor_counts_drafts_and_open_ideas_already_waiting():
    draft = {"id": "d", "stream": "regulab", "status": "draft", "date": "2026-09-30", "slot": "08:00"}
    idea = {"id": "i", "stream": "linkedin", "status": "working", "source_url": "https://x/1",
            "brief": {"position": {"date": "2026-10-01", "slot": "06:00"}}}
    store = _store([_w(1, "halal_my")], ideas=[idea], posts=_full_friday() + [draft])
    out = autofill.run(store, _floor_settings(streams=["regulab", "linkedin"]), NOW)
    assert [i["id"] for i in store.tables["semasa_ideas"]] == ["i"] and "floor" not in out        # 1 draft + 1 idea = 2


def test_floor_does_not_count_a_past_dated_draft_or_an_approved_one():
    old = {"id": "d", "stream": "regulab", "status": "draft", "date": "2026-09-20", "slot": "08:00"}
    store = _store([_w(1, "halal_my"), _w(2, "fatwa")], posts=_full_friday() + [old])
    autofill.run(store, _floor_settings(), NOW)
    assert len(store.tables["semasa_ideas"]) == 2


def test_floor_tops_up_only_the_shortfall():
    draft = {"id": "d", "stream": "regulab", "status": "draft", "date": "2026-09-30", "slot": "08:00"}
    store = _store([_w(1, "halal_my"), _w(2, "fatwa")], posts=_full_friday() + [draft])
    autofill.run(store, _floor_settings(), NOW)
    assert len(store.tables["semasa_ideas"]) == 1


def test_floor_can_be_switched_off():
    store = _store([_w(1, "halal_my"), _w(2, "fatwa")], posts=_full_friday())
    out = autofill.run(store, _floor_settings(min_drafts=0), NOW)
    assert store.tables["semasa_ideas"] == [] and "floor" not in out and "short" not in out


def test_floor_draws_a_guideline_or_new_circular_first():
    newer = {**_w(1, "halal_my"), "title": "Makluman produk baharu", "created_at": "2026-09-23T12:00:00+00:00"}
    guide = {**_w(2, "halal_my"), "title": "Garis panduan pelabelan halal", "created_at": "2026-09-20T00:00:00+00:00"}
    circular = {**_w(3, "halal_my"), "title": "Pekeliling baharu pensijilan", "created_at": "2026-09-19T00:00:00+00:00"}
    store = _store([newer, guide, circular], posts=_full_friday())
    autofill.run(store, _floor_settings(), NOW)
    by_slot = {i["brief"]["position"]["slot"]: i["source_title"] for i in store.tables["semasa_ideas"]}
    assert sorted(by_slot.values()) == ["Garis panduan pelabelan halal", "Pekeliling baharu pensijilan"]


def test_floor_skips_video_slots_and_never_writes_a_film():
    brand = {**BRAND, "regulab": {**BRAND["regulab"], "slot_formats": {"08:00": "video"}}}
    store = _store([_w(1, "halal_my"), _w(2, "fatwa")], posts=_full_friday())
    autofill.run(store, {**_floor_settings(), "brand": brand}, NOW)
    got = sorted((i["brief"]["position"]["date"], i["brief"]["position"]["slot"]) for i in store.tables["semasa_ideas"])
    assert got == [("2026-09-27", "13:00"), ("2026-09-28", "13:00")]      # 08:00 is a film slot: skipped; Mon has no rota
    assert not store.tables.get("semasa_motions")


def test_floor_takes_turns_between_streams():
    store = _store([_w(1, "halal_my"), _w(2, "halal_my")], posts=_full_friday())
    autofill.run(store, _floor_settings(streams=["regulab", "linkedin"]), NOW)
    got = sorted((i["stream"], i["brief"]["position"]["date"], i["brief"]["position"]["slot"])
                 for i in store.tables["semasa_ideas"])
    assert got == [("linkedin", "2026-09-28", "06:00"), ("regulab", "2026-09-27", "08:00")]    # Mon is a LinkedIn day


def test_floor_says_so_when_nothing_fits_and_writes_nothing():
    store = _store([], posts=_full_friday())
    out = autofill.run(store, _floor_settings(), NOW)
    assert store.tables["semasa_ideas"] == []
    assert "still 2 short of 2 waiting drafts" in out


def test_floor_never_reuses_a_position_the_gap_pass_just_filled():
    store = _store([_w(i, "kosmetik") for i in range(1, 7)])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 3, "per_run": 1,
                                                       "streams": ["regulab"], "min_drafts": 3}}, NOW)
    spots = [(i["brief"]["position"]["date"], i["brief"]["position"]["slot"]) for i in store.tables["semasa_ideas"]]
    assert len(spots) == 3 and len(set(spots)) == 3                          # 1 from the gap pass (per_run 1) + 2 from the floor


def test_a_row_with_no_words_is_never_a_candidate():
    # 25 Nov 2026: spreadsheet cells titled "40" and "0" sat in the OneDrive angle bank and the floor wrote ideas from them
    bank = [{**_w(i, "kosmetik", "folder"), "title": t, "summary": t} for i, t in ((7, "40"), (8, "0"), (9, "  "))]
    store = _store([*bank, _w(1, "kosmetik")])
    assert [c["id"] for c in autofill.candidates(store, NOW)] == ["w1"]
    assert autofill.usable_title("Garis panduan baharu") and autofill.usable_title("Notis 1")
    assert not autofill.usable_title("40") and not autofill.usable_title(None) and not autofill.usable_title("*0*")


# ---- focus topics: DRGD, FSQD and the FAQ bank (Wan, 25 Nov 2026) ---------------------------------------------------
OPEN = {"regulab": {"slots": ["08:00", "13:00", "21:00"]}, "linkedin": {"slots": ["06:00"]}}      # no rota: every domain fits


def _faq(i, category="farmaseutikal", **over):
    return {"id": f"q{i}", "status": "ready", "needs_check": False, "category": category, "answer_source": "given",
            "question_bm": f"Soalan lazim nombor {i}?",
            "answer_bm": "Jawapan penuh yang menerangkan perkara ini dengan jelas dan lengkap.",
            "instrument": "DRGD 2026, Bahagian 2", "created_at": "2026-11-20T00:00:00+00:00", **over}


def _focus_store(watch, faqs=(), ideas=()):
    return FakeStore(semasa_watch=list(watch), semasa_ideas=list(ideas), semasa_posts=[], semasa_log=[], semasa_faqs=list(faqs))


def _fs(**over):
    return {"brand": OPEN, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 3, "streams": ["regulab"],
                                         "min_drafts": 0, **over}}


def test_topic_of_names_drgd_fsqd_and_faq():
    t = autofill.topic_of
    assert t({"section": "faq", "title": "x"}) == "faq"
    assert t({"section": "regulatory", "title": "Pindaan DRGD 2026", "domain": "kosmetik"}) == "drgd"
    assert t({"section": "website", "title": "Pendaftaran produk", "domain": "farmaseutikal"}) == "drgd"
    assert t({"section": "regulatory", "title": "Notis FSQD tentang label", "domain": "halal_my"}) == "fsqd"
    assert t({"section": "regulatory", "title": "Recall susu", "domain": "makanan"}) == "fsqd"
    assert t({"section": "publication", "title": "Satu kajian", "domain": "makanan"}) is None      # a paper is not the division
    assert t({"section": "regulatory", "title": "Notis kosmetik", "domain": "kosmetik"}) is None


def test_the_faq_bank_gives_only_given_answers_with_an_instrument_that_no_idea_used():
    used = {"id": "i1", "source_name": "FAQ Semasa", "source_title": "Soalan lazim nombor 5?", "brief": {"faq_id": "q4"}}
    faqs = [_faq(1), _faq(2, needs_check=True), _faq(3, answer_source="ai"), _faq(4), _faq(5), _faq(6, instrument=""),
            _faq(7, answer_bm="pendek"), _faq(8, category="lain"), _faq(9, category="halal")]
    got = autofill.faq_candidates(_focus_store([], faqs, [used]))
    assert [c["id"] for c in got] == ["faq:q1", "faq:q9"]            # q4 by id, q5 by its question; the rest fail a rule
    assert got[0]["domain"] == "farmaseutikal" and got[1]["domain"] == "halal_my"
    assert got[0]["summary"].endswith("Sumber: DRGD 2026, Bahagian 2") and got[0]["raw"] == {"faq_id": "q1"}


def test_one_draft_in_three_is_a_focus_topic_when_one_fits():
    titles = ["Hidrokuinon ditemui dalam krim pemutih", "Merkuri dalam bedak muka dilarang", "Tretinoin pada serum jerawat",
              "Sibutramin dalam kopi kurus ditarik", "Steroid pada losyen ekzema diharamkan"]
    plain = [{**_w(i, "kosmetik"), "title": t, "summary": t.split()[0], "created_at": f"2026-09-2{i % 3}T0{i}:00:00+00:00"}
             for i, t in enumerate(titles, 1)]
    drgd = {**_w(9, "farmaseutikal"), "title": "Garis panduan DRGD terkini", "summary": "Pendaftaran ubat",
            "created_at": "2026-09-20T00:00:00+00:00"}
    store = _focus_store([*plain, drgd])
    autofill.run(store, _fs(), NOW)
    ideas = sorted(store.tables["semasa_ideas"], key=lambda i: (i["brief"]["position"]["date"], i["brief"]["position"]["slot"]))
    assert [i["brief"].get("focus") for i in ideas] == ["drgd", None, None]     # the first position is due one; then two ordinary


def test_the_faq_bank_fills_a_focus_position_and_the_idea_carries_the_answer():
    store = _focus_store([{**_w(1, "kosmetik"), "title": "Notis produk kosmetik"}], faqs=[_faq(1, "makanan")])
    autofill.run(store, _fs(), NOW)
    first = min(store.tables["semasa_ideas"], key=lambda i: (i["brief"]["position"]["date"], i["brief"]["position"]["slot"]))
    assert first["source_name"] == "FAQ Semasa" and first["source_url"] is None and first["domain"] == "makanan"
    assert first["source_title"] == "Soalan lazim nombor 1?" and first["source_summary"].endswith("Sumber: DRGD 2026, Bahagian 2")
    assert first["brief"]["faq_id"] == "q1" and first["brief"]["focus"] == "faq" and "watch_id" not in first["brief"]
    assert first["brief"]["source_priority"] == "official" and first["status"] == "new"


def test_focus_off_leaves_the_pick_and_the_pool_as_they_were():
    plain = [{**_w(i, "kosmetik"), "title": f"Notis produk kosmetik {i}"} for i in range(1, 4)]
    drgd = {**_w(9, "farmaseutikal"), "title": "Garis panduan DRGD terkini", "created_at": "2026-09-01T00:00:00+00:00"}
    store = _focus_store([*plain, drgd], faqs=[_faq(1)])
    autofill.run(store, _fs(focus=[]), NOW)
    assert all("focus" not in i["brief"] and i["source_name"] != "FAQ Semasa" for i in store.tables["semasa_ideas"])
    assert autofill.config({"autofill": {"enabled": True, "focus": ["drgd", "x"]}})["focus"] == ["drgd"]
    assert autofill.config({"autofill": {"enabled": True}})["focus"] == ["drgd", "fsqd", "faq"]


def test_the_share_holds_across_runs_from_the_latest_auto_ideas():
    done = lambda f: {"brief": {"auto": True, **({"focus": "faq"} if f else {})}}      # noqa: E731
    cfg = {"focus": ["drgd", "fsqd", "faq"], "focus_every": 3}
    assert autofill.Focus.load(_focus_store([], ideas=[]), cfg).prefer() == {"drgd", "fsqd", "faq"}     # nothing yet: due
    after_focus = autofill.Focus(cfg["focus"], 3, [done(True)])
    assert after_focus.prefer() is None                                  # 1 focus in 1 idea: the next two are ordinary
    after_focus.wrote({"section": "regulatory", "title": "x", "domain": "kosmetik"})
    assert after_focus.prefer() is None
    after_focus.wrote({"section": "regulatory", "title": "y", "domain": "kosmetik"})
    assert after_focus.prefer() == {"drgd", "fsqd", "faq"}               # 1 in 3: due again


def test_linkedin_never_takes_an_faq_row():
    store = _focus_store([], faqs=[_faq(1)])
    autofill.run(store, _fs(streams=["linkedin"], days_ahead=3), NOW)
    assert store.tables["semasa_ideas"] == []


# ---- the feed window and the silent runs (26 Nov 2026) --------------------------------------------------------
def test_official_rows_are_not_crowded_out_of_the_window_by_social_rows():
    social = [{**_w(100 + i, "kosmetik", "expert"), "title": f"Hantaran pakar nombor {i} tentang sesuatu",
               "created_at": "2026-09-23T12:00:00+00:00"} for i in range(250)]
    old_notice = {**_w(1, "kosmetik"), "title": "Garis panduan baharu label", "created_at": "2026-09-10T00:00:00+00:00"}
    got = autofill.candidates(_store([*social, old_notice]), NOW)
    assert [c["id"] for c in got] == ["w1"]      # older than 250 social rows, still read; and no social row is a candidate


def _stamp(store):
    """The database stamps a log row's `at` itself; the fake store does not."""
    from datetime import UTC, datetime
    for r in store.tables["semasa_log"]:
        r["at"] = datetime.now(UTC).isoformat()


def test_a_run_that_writes_nothing_says_why_once():
    store = _store([])
    cfg = _fs(min_drafts=2)
    autofill.run(store, cfg, NOW)
    _stamp(store)
    autofill.run(store, cfg, NOW)                                         # a second silent run adds no second line
    lines = [r for r in store.tables["semasa_log"] if r.get("event") == "idea.autofill_idle"]
    assert len(lines) == 1 and "kolam 0" in lines[0]["title"] and lines[0]["detail"]["floor_short"] == 2


def test_a_run_that_dies_says_so_once():
    class Broken(FakeStore):
        def table(self, name):
            if name == "semasa_watch":
                raise RuntimeError("the feed table is gone")
            return super().table(name)
    store = Broken(semasa_watch=[], semasa_ideas=[], semasa_posts=[], semasa_log=[])
    assert autofill.run(store, _fs(), NOW).startswith("Autofill: skipped")
    _stamp(store)
    autofill.run(store, _fs(), NOW)
    lines = [r for r in store.tables["semasa_log"] if r.get("event") == "idea.autofill_error"]
    assert len(lines) == 1 and "the feed table is gone" in lines[0]["title"]


# ---- unofficial sources, after every official item (Wan, 26 Nov 2026) -------------------------------------------
SOCIAL_TITLES = ["Sunscreen cair bila berpeluh betul ke", "Serum vitamin C tak boleh campur retinol",
                 "Krim pemutih murah di Shopee",
                 "Pewangi buah-buahan cepat hilang bau"]


def _social(i, section, domain="kosmetik"):
    return {**_w(50 + i, domain, section), "title": SOCIAL_TITLES[i - 1], "url": f"https://{section}.example/{i}",
            "summary": f"Soalan {i}"}


def test_unofficial_rows_fill_after_every_official_item_and_are_flagged_for_the_reviewer():
    store = _store([_w(1, "kosmetik"), _social(1, "threads"), _social(2, "reddit"), _social(3, "expert")])
    autofill.run(store, _fs(per_run=3, min_drafts=0, focus=[]), NOW)
    made = sorted(store.tables["semasa_ideas"], key=lambda i: (i["brief"]["position"]["date"], i["brief"]["position"]["slot"]))
    assert [m["source_url"] for m in made] == ["https://npra.gov.my/1", "https://threads.example/1", "https://reddit.example/2"]
    assert "unofficial" not in made[0]["brief"] and made[0]["brief"]["source_priority"] == "official"
    assert made[1]["brief"]["unofficial"] is True and made[1]["brief"]["relate_regulatory"] is True
    assert made[1]["brief"]["source_priority"] == "current" and made[1]["status"] == "new"   # still only an idea: Wan approves
    assert all("expert" not in m["source_url"] for m in made)                                # the AI experts never fill a slot


def test_unofficial_can_be_switched_off_and_linkedin_never_takes_it():
    store = _store([_social(1, "threads"), _social(2, "reddit")])
    autofill.run(store, _fs(per_run=3, min_drafts=0, focus=[], unofficial=False), NOW)
    assert store.tables["semasa_ideas"] == []
    store = _store([_social(1, "threads")])
    autofill.run(store, _fs(per_run=3, min_drafts=0, focus=[], streams=["linkedin"], days_ahead=3), NOW)
    assert store.tables["semasa_ideas"] == []


def test_an_faq_answer_comes_before_a_social_post():
    faq = autofill.faq_candidates(_focus_store([], [_faq(1, "kosmetik")]))
    ranked = autofill.rank_candidates([_social(1, "threads"), *faq])
    assert [x["section"] for x in ranked] == ["faq", "threads"]


# --- ws.regulab limited to fatwa (Wan, 26 Nov 2026: stop ws.regulab research, "buatkan autofill" for fatwa) ----------------

def _fatwa_settings(**extra):
    return {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 3, "per_run": 5, "min_drafts": 0, "streams": ["regulab"],
                                         "regulab_only": ["fatwa"], **extra}}


def test_regulab_only_reads_a_list_of_known_domains_and_nothing_else():
    assert autofill.config({"autofill": {"regulab_only": ["fatwa"]}})["regulab_only"] == ["fatwa"]
    assert autofill.config({"autofill": {"regulab_only": ["fatwa", "nonsense", "lain"]}})["regulab_only"] == ["fatwa"]
    assert autofill.config({"autofill": {"regulab_only": "fatwa"}})["regulab_only"] == []
    assert autofill.config({"autofill": {}})["regulab_only"] == []


def test_regulab_writes_only_fatwa_when_limited_to_it():
    store = _store([_w(1, "halal_my"), _w(2, "kosmetik"), _w(3, "fatwa"), _w(4, "fatwa")])
    autofill.run(store, _fatwa_settings(), NOW)
    ideas = store.tables["semasa_ideas"]
    assert sorted(i["source_url"][-1] for i in ideas) == ["3", "4"] and all(i["domain"] == "fatwa" for i in ideas)
    assert {i["brief"]["position"]["date"] for i in ideas} == {"2026-09-27"}          # Sunday: the rota gives fatwa that day


def test_without_the_limit_regulab_still_takes_every_domain():
    store = _store([_w(1, "halal_my"), _w(2, "kosmetik"), _w(3, "fatwa")])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 3, "per_run": 5, "min_drafts": 0,
                                                       "streams": ["regulab"]}}, NOW)
    assert {i["domain"] for i in store.tables["semasa_ideas"]} == {"halal_my", "kosmetik", "fatwa"}


def test_the_floor_never_pulls_a_non_fatwa_item_into_regulab_when_limited():
    store = _store([_w(1, "halal_my"), _w(2, "kosmetik")])
    out = autofill.run(store, _fatwa_settings(min_drafts=2), NOW)
    assert store.tables["semasa_ideas"] == [] and "short" in out


def test_the_floor_writes_a_fatwa_item_into_regulab_when_limited():
    store = _store([_w(3, "fatwa"), _w(2, "kosmetik")])
    autofill.run(store, _fatwa_settings(min_drafts=2, days_ahead=1), NOW)
    assert [i["domain"] for i in store.tables["semasa_ideas"]] == ["fatwa"]


def test_the_limit_never_touches_linkedin():
    store = _store([_w(i, "kosmetik", "publication") for i in range(3)])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 7, "per_run": 2, "min_drafts": 0,
                                                       "streams": ["regulab", "linkedin"], "regulab_only": ["fatwa"]}}, NOW)
    assert all(i["stream"] == "linkedin" for i in store.tables["semasa_ideas"]) and store.tables["semasa_ideas"]


# --- a paper a week on LinkedIn, and LinkedIn tells it as a story (Wan, 27 Nov 2026) -----------------------------------------

TOPICS = ["niacinamide dan kulit berminyak", "retinol pada wanita hamil", "tabir suria mineral dan terumbu",
          "kolagen oral dan kedutan", "probiotik topikal untuk ekzema"]


def _paper(i):
    return {**_w(i, "sains_kosmetik", "publication"), "title": f"Kajian {TOPICS[(i - 1) % len(TOPICS)]} diterbitkan Jurnal {i}"}


def _li_settings(**extra):
    return {"brand": {**BRAND, "linkedin": {"slots": ["06:00"], "days": [1, 3, 5]}},
            "autofill": {"enabled": True, "days_ahead": 7, "per_run": 5, "min_drafts": 0, "streams": ["linkedin"], **extra}}


def test_the_paper_quota_defaults_to_one_a_week_and_clamps():
    assert autofill.config({})["linkedin_papers"] == 1
    assert autofill.config({"autofill": {"linkedin_papers_per_week": 0}})["linkedin_papers"] == 0
    assert autofill.config({"autofill": {"linkedin_papers_per_week": 3}})["linkedin_papers"] == 3
    assert autofill.config({"autofill": {"linkedin_papers_per_week": 99}})["linkedin_papers"] == 7
    assert autofill.config({"autofill": {"linkedin_papers_per_week": "many"}})["linkedin_papers"] == 1


def test_a_week_is_counted_from_its_monday():
    assert autofill.PaperQuota.week("2026-09-27") == "2026-09-21"           # a Sunday belongs to the week before it
    assert autofill.PaperQuota.week("2026-09-28") == "2026-09-28"
    assert autofill.PaperQuota.week("2026-10-02") == "2026-09-28"


def test_linkedin_takes_one_paper_a_week_and_never_a_second_in_the_same_week():
    store = _store([_paper(i) for i in range(1, 6)])
    autofill.run(store, _li_settings(), NOW)
    ideas = store.tables["semasa_ideas"]
    dates = sorted(i["brief"]["position"]["date"] for i in ideas)
    # Thu 24 Sep: Fri 25 is the week of 21 Sep; Mon 28 and Wed 30 are one week, so only one of those two gets a paper
    assert dates == ["2026-09-25", "2026-09-28"] and all(i["angle"] == "F" for i in ideas)


def test_a_paper_already_written_for_a_week_closes_that_week_whatever_its_status_but_not_a_rejected_one():
    posts = [{"id": "p1", "stream": "linkedin", "status": "scheduled", "date": "2026-09-29", "slot": "06:00", "angle": "F"},
             {"id": "p2", "stream": "linkedin", "status": "rejected", "date": "2026-09-25", "slot": "06:00", "angle": "F"}]
    store = _store([_paper(i) for i in range(1, 6)], posts=posts)
    autofill.run(store, _li_settings(), NOW)
    dates = sorted(i["brief"]["position"]["date"] for i in store.tables["semasa_ideas"])
    assert dates == ["2026-09-25"]            # 28 Sep's week is full (29 Sep paper); the rejected 25 Sep one holds nothing


def test_a_paper_idea_still_being_written_counts_too():
    waiting_idea = {"id": "i1", "stream": "linkedin", "status": "new", "angle": "F", "source_url": "https://x/1",
                    "brief": {"position": {"date": "2026-09-25", "slot": "06:00"}}}
    store = _store([_paper(i) for i in range(1, 6)], ideas=[waiting_idea])
    autofill.run(store, _li_settings(), NOW)
    new = [i for i in store.tables["semasa_ideas"] if i["id"] != "i1"]
    assert sorted(i["brief"]["position"]["date"] for i in new) == ["2026-09-28"]


def test_the_rest_of_the_week_goes_to_guidelines_and_circulars_and_zero_means_no_paper_at_all():
    pool = [_paper(1), _paper(2), {**_w(7, "kosmetik"), "title": "Garis panduan terkini label kosmetik dikemas kini"}]
    store = _store(pool)
    autofill.run(store, _li_settings(), NOW)
    angles = sorted(i["angle"] for i in store.tables["semasa_ideas"])
    assert angles.count("F") == 1 and "A" in angles
    none = _store([_paper(i) for i in range(1, 4)])
    autofill.run(none, _li_settings(linkedin_papers_per_week=0), NOW)
    assert none.tables["semasa_ideas"] == []


def test_the_quota_never_touches_ws_regulab_and_a_failed_read_writes_no_paper():
    store = _store([_paper(1)])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 3, "per_run": 5, "min_drafts": 0,
                                                       "streams": ["regulab"]}}, NOW)
    assert all(i["stream"] == "regulab" for i in store.tables["semasa_ideas"])

    class Broken(FakeStore):
        def table(self, name):
            if name == "semasa_posts":
                raise RuntimeError("down")
            return super().table(name)
    quota = autofill.PaperQuota.read(Broken(semasa_posts=[], semasa_ideas=[]), 1, NOW)
    assert not quota.ok("2026-09-28")


def test_linkedin_is_asked_to_tell_the_true_story_in_the_format_it_has_and_ws_regulab_is_not():
    from semasa import ideas
    brand = {"linkedin": {"angles": {}}}
    li = ideas.build_request({"stream": "linkedin", "source_title": "t", "brief": {}}, {"ok": False}, brand)[1]
    assert "tell it as a story" in li and "TRUE story" in li and "no invented client" in li
    assert "numbered facts" in li and "the hashtags" in li                      # the format is named as unchanged
    rg = ideas.build_request({"stream": "regulab", "source_title": "t", "brief": {"story_mode": True}}, {"ok": False}, {})[1]
    assert "tell it as a story" not in rg and "STORY MODE" in rg
