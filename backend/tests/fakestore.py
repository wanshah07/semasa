"""An in-memory stand-in for the supabase-py query builder: just the calls the runners make."""

from __future__ import annotations

import copy
import uuid
from types import SimpleNamespace


class _Not:
    def __init__(self, q):
        self.q = q

    def is_(self, col, val):
        self.q.filters.append(lambda r: r.get(col) is not None if val == "null" else r.get(col) != val)
        return self.q


class Query:
    def __init__(self, store, table):
        self.store, self.table, self.filters = store, table, []
        self.op, self.payload, self._order, self._limit = "select", None, [], None

    # verbs
    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def upsert(self, payload, on_conflict=None, ignore_duplicates=False):
        self.op, self.payload, self._conflict, self._ignore = "upsert", payload, on_conflict, ignore_duplicates
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    # filters
    def eq(self, c, v):
        self.filters.append(lambda r: r.get(c) == v)
        return self

    def neq(self, c, v):
        self.filters.append(lambda r: r.get(c) != v)
        return self

    def lt(self, c, v):
        self.filters.append(lambda r: r.get(c) is not None and str(r.get(c)) < str(v))
        return self

    def gt(self, c, v):
        def after(r):
            x = r.get(c)
            if x is None:
                return False
            if isinstance(x, (int, float)) and isinstance(v, (int, float)):
                return x > v
            return str(x) > str(v)
        self.filters.append(after)
        return self

    def gte(self, c, v):
        self.filters.append(lambda r: r.get(c) is not None and str(r.get(c)) >= str(v))
        return self

    def in_(self, c, vals):
        vals = list(vals)
        self.filters.append(lambda r: r.get(c) in vals)
        return self

    @property
    def not_(self):
        return _Not(self)

    def order(self, col, desc=False):
        self._order.append((col, desc))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = self.store.tables.setdefault(self.table, [])
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for it in items:
                row = {"id": str(uuid.uuid4()), "status": None, **copy.deepcopy(it)}
                row.setdefault("updated_at", self.store.now)
                rows.append(row)
                out.append(copy.deepcopy(row))
            return SimpleNamespace(data=out)
        if self.op == "upsert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for it in items:
                key = it.get(self._conflict) if self._conflict else None
                old = next((r for r in rows if key is not None and r.get(self._conflict) == key), None)
                if old is not None:
                    if not self._ignore:
                        old.update(copy.deepcopy(it))
                        out.append(copy.deepcopy(old))
                    continue
                row = {"id": str(uuid.uuid4()), **copy.deepcopy(it)}
                rows.append(row)
                out.append(copy.deepcopy(row))
            return SimpleNamespace(data=out)
        hit = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(copy.deepcopy(self.payload))
            return SimpleNamespace(data=copy.deepcopy(hit))
        if self.op == "delete":
            self.store.tables[self.table] = [r for r in rows if r not in hit]
            return SimpleNamespace(data=hit)
        for col, desc in reversed(self._order):
            hit.sort(key=lambda r, c=col: (r.get(c) is None, str(r.get(c))), reverse=desc)
        if self._limit is not None:
            hit = hit[: self._limit]
        return SimpleNamespace(data=copy.deepcopy(hit))


class FakeStore:
    def __init__(self, **tables):
        self.tables = {k: copy.deepcopy(v) for k, v in tables.items()}
        self.now = "2026-09-24T00:00:00+00:00"

    def table(self, name):
        return Query(self, name)
