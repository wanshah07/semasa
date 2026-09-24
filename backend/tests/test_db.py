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
