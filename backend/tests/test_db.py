from urllib.parse import quote

from semasa import db

GNEWS = ("https://news.google.com/rss/articles/CBMivAFBVV95cUxNZTYzT1NRaHZRenE0VUNtaV93VC1fOHNieV9UWERnLTFWLXpTa0N6QzJU"
         "SDMtVE9TbmdFeFVGcW1aRkRNTDFZU1V6Mzg0cTNpNnFhUmlMME1URVlmNUxUTkswVHFreElIT0k1WEhBT2Q5ZTdtWlNuSmV0dDZKdkFjbnd6"
         "RFJxZWUzTGNYemFkaGRMRDZJS1llYWh2cWZZS0FlTVhvRjZTWTQ0MU81R1J3TGFxMTFhOG91SUtwaNIBXEFVX3lxTE4wcjlPYzY2TWw5aXRX"
         "aTlJcHl1WmpneWxXZVhRZUFkNjhHd3BCSDJlTDVFZlZwYjRoTVcyRFh4NEZfMU5XdDFDWnc2YlZsVTdrMUx6QVpXWE1uYVlL?oc=5")


def _sent_length(chunk):
    toks = [f'"{v}"' if any(c in v for c in ",:()") else v for v in chunk]
    return len(quote("(" + ",".join(toks) + ")", safe=""))


def test_chunks_stay_under_budget_and_cover_everything():
    urls = [f"{GNEWS}&n={i}" for i in range(100)]      # the batch that failed: ~45,000 chars in one request
    chunks = list(db._in_filter_chunks(urls))
    assert [u for c in chunks for u in c] == urls      # nothing lost, order kept
    assert len(chunks) > 1
    assert all(_sent_length(c) <= db.IN_FILTER_BUDGET for c in chunks)


def test_oversized_single_value_travels_alone():
    huge = "https://x.my/" + "a" * (db.IN_FILTER_BUDGET * 2)
    assert list(db._in_filter_chunks(["https://a.my/1", huge, "https://a.my/2"])) == [["https://a.my/1"], [huge], ["https://a.my/2"]]


class _FakeQuery:
    def __init__(self, store, calls):
        self.store, self.calls = store, calls

    def select(self, *_):
        return self

    def in_(self, _col, values):
        self.values = list(values)
        return self

    def execute(self):
        self.calls.append(self.values)
        if len(self.calls) == 2:
            raise RuntimeError("{'message': 'JSON could not be generated', 'code': 400}")

        class R:
            data = [{"url": v} for v in self.values if v in self.store]
        return R()


class _FakeDB:
    def __init__(self, store):
        self.store, self.calls = store, []

    def table(self, _name):
        return _FakeQuery(self.store, self.calls)


def test_a_failed_batch_does_not_crash_and_other_batches_still_count():
    urls = [f"{GNEWS}&n={i}" for i in range(60)]
    fake = _FakeDB(store=set(urls[:5]) | {urls[-1]})
    found = db.existing_urls(fake, urls)
    assert len(fake.calls) >= 3                         # batch 2 raised, the rest still ran
    assert set(urls[:5]) <= found and urls[-1] in found


def test_a_run_for_one_job_takes_it_first_and_fills_the_batch():
    # a slide waiting for its post's picture used to re-dispatch runs for the slide alone until SLIDES_WAIT ran out
    from fakestore import FakeStore

    from semasa import db
    store = FakeStore(media_generations=[
        {"id": "pic", "status": "pending", "created_at": "2026-09-26T10:00:00+00:00", "attempts": 0},
        {"id": "slide", "status": "pending", "created_at": "2026-09-26T10:00:01+00:00", "attempts": 0},
        {"id": "done", "status": "done", "created_at": "2026-09-26T09:00:00+00:00", "attempts": 1}])
    got = [r["id"] for r in db.claim_pending(store, 5, "slide")]
    assert got == ["slide", "pic"]
    statuses = {r["id"]: r["status"] for r in store.tables["media_generations"]}
    assert statuses == {"pic": "processing", "slide": "processing", "done": "done"}


def test_a_one_job_run_respects_the_batch_size():
    from fakestore import FakeStore

    from semasa import db
    store = FakeStore(media_generations=[{"id": f"r{i}", "status": "pending", "created_at": f"2026-09-26T10:00:0{i}+00:00",
                                          "attempts": 0} for i in range(4)])
    assert [r["id"] for r in db.claim_pending(store, 2, "r3")] == ["r3", "r0"]


def test_one_refused_stuck_row_does_not_keep_the_others_stuck():
    """Before 018, the database refused to put back an idea whose draft had been approved, and that one refusal failed
    the whole recovery statement, so every stuck idea stayed `working` for ever."""
    from semasa import db
    from tests.fakestore import FakeStore
    old = "2026-09-24T00:00:00+00:00"
    store = FakeStore(semasa_ideas=[{"id": i, "status": "working", "attempts": 1, "updated_at": old} for i in ("A", "B", "C")])
    real_table = store.table

    def table(name):
        q = real_table(name)
        run = q.execute

        def execute():
            if q.op == "update" and (q.payload or {}).get("status") == "new":
                hit = [r for r in store.tables[name] if all(f(r) for f in q.filters)]
                if any(r["id"] == "B" for r in hit):
                    raise RuntimeError("semasa: this idea already has a approved post")
            return run()
        q.execute = execute
        return q
    store.table = table
    n = db.requeue_stale(store, "semasa_ideas", working="working", back="new", cutoff="2026-09-25T00:00:00+00:00",
                         max_attempts=3, what="idea")
    status = {r["id"]: r["status"] for r in store.tables["semasa_ideas"]}
    assert n == 2 and status == {"A": "new", "B": "working", "C": "new"}
