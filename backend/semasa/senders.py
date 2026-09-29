"""The two roads out of Semasa, brought over from ws.regulab Studio (Wan, 29 Sep 2026: "we will start using semasa this
friday and will delete ws.regulab studio permanently").

  Buffer   — ws.regulab's Facebook, Instagram and Threads. Buffer's own queue fires the post at its slot, so a post is
             handed over as soon as it is approved (`customScheduled` for its own time), exactly as Studio did.
  Composio — Wan's LinkedIn profile, text alone or with its card(s). LinkedIn has no queue: the post goes the moment
             it is called, so the publisher only calls it once the slot has come.

Both are plain HTTPS from the GitHub runner, keyed by repository secrets (BUFFER_API_KEY, COMPOSIO_API_KEY). Nothing
here decides WHETHER to send; that is publisher.py, behind the approval gate and the compliance scan. This module only
knows how to send, how to read back what the network did, and how to name a failure so the publisher treats it right:

  full       Buffer's plan cap on scheduled posts per channel. A WAIT, never an error: it clears when a post fires.
  transient  the network hiccuped ("having issues", timeouts, rate limits, media processing). One identical retry.
  refused    anything else (caption too long, picture rejected). Never retried: a retry would post it twice.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

# Studio's own patterns (argus studio/part2.html BUFFER_FULL / TRANSIENT_SEND), kept word for word.
BUFFER_FULL = re.compile(r"limit reached|scheduled posts limit|plan limit", re.I)
TRANSIENT = re.compile(
    r"having issues|please (?:check|try) .*retry|try again|temporar|timed? ?out|timeout|internal error|unknown error"
    r"|rate ?limit|too many requests|processing the attached media|media (?:processing|upload) (?:failed|error)", re.I)

BUFFER_URL = os.environ.get("BUFFER_API_URL", "https://api.buffer.com")
COMPOSIO_URL = os.environ.get("COMPOSIO_BASE_URL", "https://backend.composio.dev")
LINKEDIN_TOOL = "LINKEDIN_CREATE_LINKED_IN_POST"


class SendError(Exception):
    """kind: 'full' | 'transient' | 'refused'."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def classify(message: str) -> str:
    if BUFFER_FULL.search(message or ""):
        return "full"
    if TRANSIENT.search(message or ""):
        return "transient"
    return "refused"


def text_key(text: str) -> str:
    """How a caption is recognised in Buffer: its first 100 letters, whitespace squeezed (Studio's tally matched on the
    first hundred letters too)."""
    return re.sub(r"\s+", " ", str(text or "")).strip()[:100]


# --- Buffer --------------------------------------------------------------------------------------------------------

_POST_FIELDS = "id status dueAt sentAt text channelId externalLink error { message }"


class Buffer:
    """Buffer's GraphQL API. One key, one organization, the three ws.regulab channels."""

    def __init__(self, api_key: str, organization_id: str, session: Any = None, url: str = BUFFER_URL,
                 sleep=time.sleep):
        self.key, self.org, self.url = api_key, organization_id, url.rstrip("/")
        self.http = session or requests.Session()
        self.sleep = sleep

    def _gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            r = self.http.post(self.url, json={"query": query, "variables": variables or {}}, timeout=60,
                               headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        except requests.RequestException as exc:
            raise SendError("transient", f"Buffer unreachable: {exc}") from exc
        if r.status_code == 429:
            raise SendError("transient", "Buffer rate limit (429)")
        if r.status_code >= 500:
            raise SendError("transient", f"Buffer answered {r.status_code}")
        try:
            body = r.json()
        except ValueError as exc:
            raise SendError("refused", f"Buffer answered {r.status_code} with no JSON") from exc
        if body.get("errors"):
            msg = "; ".join(str(e.get("message")) for e in body["errors"])
            raise SendError(classify(msg), f"Buffer: {msg}")
        return body.get("data") or {}

    def create(self, channel_id: str, service: str, text: str, pictures: list[str], alt: str,
               due_at: str | None) -> dict[str, Any]:
        """Hand one post to one channel. `due_at` None means share now (a post whose slot has just come)."""
        inp: dict[str, Any] = {"channelId": channel_id, "text": text, "schedulingType": "automatic",
                               "saveToDraft": False, "mode": "customScheduled" if due_at else "shareNow",
                               "assets": [{"image": {"url": u, "metadata": {"altText": (alt or "")[:1000]}}}
                                          for u in pictures]}
        if due_at:
            inp["dueAt"] = due_at
        if service == "facebook":
            inp["metadata"] = {"facebook": {"type": "post"}}
        elif service == "instagram":
            inp["metadata"] = {"instagram": {"type": "post", "shouldShareToFeed": False}}
        data = self._gql(
            "mutation($input: CreatePostInput!) { createPost(input: $input) { __typename "
            f"... on PostActionSuccess {{ post {{ {_POST_FIELDS} }} }} ... on MutationError {{ message }} }} }}",
            {"input": inp})
        out = data.get("createPost") or {}
        if out.get("__typename") != "PostActionSuccess":
            msg = out.get("message") or out.get("__typename") or "no answer"
            raise SendError(classify(msg), f"Buffer refused: {msg}")
        return out["post"]

    def get(self, post_id: str) -> dict[str, Any]:
        data = self._gql(f"query($input: PostInput!) {{ post(input: $input) {{ {_POST_FIELDS} }} }}",
                         {"input": {"id": post_id}})
        return data.get("post") or {}

    def posts(self, channel_ids: list[str], start: str, end: str) -> list[dict[str, Any]]:
        """Every post on these channels due in [start, end], any status, for the no-double-post check and the tally."""
        out: list[dict[str, Any]] = []
        after = None
        for _ in range(20):
            data = self._gql(
                "query($input: PostsInput!, $after: String) { posts(input: $input, first: 50, after: $after) { "
                f"edges {{ node {{ {_POST_FIELDS} }} }} pageInfo {{ hasNextPage endCursor }} }} }}",
                {"input": {"organizationId": self.org,
                           "filter": {"channelIds": channel_ids, "dueAt": {"start": start, "end": end}}},
                 "after": after})
            page = data.get("posts") or {}
            out += [e["node"] for e in page.get("edges") or []]
            info = page.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                break
            after = info.get("endCursor")
        return out

    def confirm(self, post_id: str, tries: int = 10, every: float = 3.0) -> dict[str, Any]:
        """Buffer accepting a post is not the network publishing it: for a share-now, read it back until it settles."""
        last: dict[str, Any] = {}
        for _ in range(tries):
            last = self.get(post_id)
            if last.get("status") in ("sent", "error"):
                return last
            self.sleep(every)
        return {**last, "unconfirmed": True}


# --- Composio (LinkedIn) -------------------------------------------------------------------------------------------

def _message(body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        return str(body.get("message") or err or body)[:500]
    return str(body)[:500]


@dataclass
class LinkedInResult:
    urn: str
    url: str


class LinkedIn:
    """Composio's REST API with a project key. The connected LinkedIn account is found by the key itself, so the
    runner needs no account id: exactly one ACTIVE LinkedIn connection must exist, or nothing is sent."""

    def __init__(self, api_key: str, author: str, session: Any = None, url: str = COMPOSIO_URL,
                 account_id: str | None = None):
        self.key, self.author, self.url = api_key, author, url.rstrip("/")
        self.http = session or requests.Session()
        self.account_id = account_id

    def _call(self, method: str, path: str, **kw) -> dict[str, Any]:
        try:
            r = self.http.request(method, self.url + path, timeout=120,
                                  headers={"x-api-key": self.key, "Content-Type": "application/json"}, **kw)
        except requests.RequestException as exc:
            raise SendError("transient", f"Composio unreachable: {exc}") from exc
        if r.status_code == 429 or r.status_code >= 500:
            raise SendError("transient", f"Composio answered {r.status_code}")
        try:
            body = r.json()
        except ValueError as exc:
            raise SendError("refused", f"Composio answered {r.status_code} with no JSON") from exc
        if r.status_code >= 400:
            msg = _message(body)
            raise SendError(classify(msg), f"Composio {r.status_code}: {msg}")
        return body

    def account(self) -> str:
        if self.account_id:
            return self.account_id
        body = self._call("GET", "/api/v3/connected_accounts",
                          params={"toolkit_slugs": "linkedin", "statuses": "ACTIVE", "limit": 50})
        items = body.get("items") or []
        if len(items) != 1:
            raise SendError("refused", f"Composio: expected exactly 1 active LinkedIn connection, found {len(items)}")
        self.account_id = items[0]["id"]
        return self.account_id

    def upload(self, content: bytes, filename: str, mimetype: str) -> dict[str, str]:
        """Composio's presigned upload (the SDK's own route, composio/core/models/_files.py): ask for a URL, PUT the
        bytes, keep the key. The picture's bytes go runner -> S3 and never through anything else."""
        meta = self._call("POST", "/api/v3/files/upload/request",
                          json={"md5": hashlib.md5(content, usedforsecurity=False).hexdigest(), "filename": filename,
                                "mimetype": mimetype, "tool_slug": LINKEDIN_TOOL, "toolkit_slug": "linkedin"})
        try:
            put = self.http.put(meta["new_presigned_url"], data=content, headers={"Content-Type": mimetype},
                                timeout=120)
        except requests.RequestException as exc:
            raise SendError("transient", f"picture upload failed: {exc}") from exc
        if put.status_code >= 300:
            raise SendError("transient", f"picture upload answered {put.status_code}")
        return {"name": filename, "mimetype": mimetype, "s3key": meta["key"]}

    def fetch_picture(self, url: str, n: int) -> tuple[bytes, str, str]:
        try:
            r = self.http.get(url, timeout=60)
        except requests.RequestException as exc:
            raise SendError("transient", f"picture {n} unreachable: {exc}") from exc
        ctype = (r.headers.get("content-type") or "").split(";")[0].strip()
        if r.status_code != 200 or not ctype.startswith("image/"):
            raise SendError("refused", f"picture {n} answered {r.status_code} {ctype or 'no type'}: {url}")
        ext = mimetypes.guess_extension(ctype) or ".jpg"
        return r.content, f"slide-{n:02d}{ext}", ctype

    def post(self, text: str, pictures: list[str]) -> LinkedInResult:
        images = [self.upload(*self.fetch_picture(u, i + 1)) for i, u in enumerate(pictures[:20])]
        args: dict[str, Any] = {"author": self.author, "commentary": text, "visibility": "PUBLIC"}
        if images:
            args["images"] = images
        body = self._call("POST", f"/api/v3.1/tools/execute/{LINKEDIN_TOOL}",
                          json={"connected_account_id": self.account(), "arguments": args})
        if not body.get("successful"):
            msg = str(body.get("error") or "no reason given")
            raise SendError(classify(msg), f"LinkedIn refused: {msg}")
        data = body.get("data") or {}
        urn = data.get("x_restli_id") or data.get("id") or ""
        if not urn.startswith("urn:li:"):
            # it may have posted: never let the publisher try again on its own
            raise SendError("refused", f"LinkedIn answered without a post id: {str(data)[:300]}")
        return LinkedInResult(urn=urn, url=f"https://www.linkedin.com/feed/update/{urn}/")
