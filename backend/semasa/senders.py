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
LINKEDIN_VIDEO_UPLOAD = "LINKEDIN_UPLOAD_VIDEO"       # a public MP4 address -> an urn:li:video once LinkedIn has it ready
LINKEDIN_VIDEO_POST = "LINKEDIN_CREATE_VIDEO_POST"    # that urn + the words -> a native video post


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
    """How a caption is recognised in Buffer: ALL of it, whitespace squeezed. Studio's tally matched the first hundred
    letters only, and two different posts that open the same way (a series, a regulator's standard first line) then read
    as one: the second was "adopted" onto the first one's Buffer post and never sent."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


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
        return self._create_post(inp)

    def create_video(self, channel_id: str, service: str, text: str, video: dict[str, Any],
                     due_at: str | None) -> dict[str, Any]:
        """A post whose one asset is a video (Wan, 26 Oct 2026: a Motion film queued to a platform). `video` is
        {url, thumbnail, vertical}: a vertical film is a Reel on Facebook and Instagram (Instagram's Reels also show in the
        feed), anything else a plain post. Threads takes the video as it is."""
        # Buffer refuses a video asset carrying thumbnailUrl ("Video thumbnailUrl is not supported", 10 posts on 6 Nov 2026):
        # the network takes its own cover frame
        asset: dict[str, Any] = {"url": video["url"]}
        inp: dict[str, Any] = {"channelId": channel_id, "text": text, "schedulingType": "automatic",
                               "saveToDraft": False, "mode": "customScheduled" if due_at else "shareNow",
                               "assets": [{"video": asset}]}
        if due_at:
            inp["dueAt"] = due_at
        reel = bool(video.get("vertical"))
        if service == "facebook":
            inp["metadata"] = {"facebook": {"type": "reel" if reel else "post"}}
        elif service == "instagram":
            inp["metadata"] = {"instagram": {"type": "reel" if reel else "post", "shouldShareToFeed": True}}
        return self._create_post(inp)

    def _create_post(self, inp: dict[str, Any]) -> dict[str, Any]:
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

    def sent_with_metrics(self, channel_ids: list[str], start: str, end: str) -> list[dict[str, Any]]:
        """Every SENT post on these channels, due in [start, end], with Buffer's own per-post figures (Prestasi,
        metrics.py). Buffer refreshes the figures about once a day; `metricsUpdatedAt` says when."""
        out: list[dict[str, Any]] = []
        after = None
        for _ in range(40):
            data = self._gql(
                "query($input: PostsInput!, $after: String) { posts(input: $input, first: 50, after: $after) { "
                "edges { node { id status channelId channelService dueAt sentAt text externalLink metricsUpdatedAt "
                "metrics { type value unit } } } pageInfo { hasNextPage endCursor } } }",
                {"input": {"organizationId": self.org,
                           "filter": {"channelIds": channel_ids, "status": ["sent"], "dueAt": {"start": start, "end": end}},
                           "sort": [{"field": "dueAt", "direction": "desc"}]},
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


# --- Zernio ---------------------------------------------------------------------------------------------------------

ZERNIO_URL = "https://zernio.com/api/v1"
ZERNIO_STATUS = {"scheduled": "scheduled", "pending": "scheduled", "publishing": "sending", "published": "sent",
                 "failed": "error", "partial": "error", "draft": "draft", "cancelled": "error"}
THREAD_MAX = 500                # one Threads post
THREAD_LEVELS = 5               # the levels of one chain (Wan, 10 Nov 2026: "bertingkat post dalam 1 post")
TIKTOK_SETTINGS = {"privacy_level": "PUBLIC_TO_EVERYONE", "allow_comment": True, "allow_duet": True, "allow_stitch": True,
                   "commercial_content_type": "none", "content_preview_confirmed": True, "express_consent_given": True,
                   "media_type": "video", "auto_add_music": False, "video_made_with_ai": True}


_TAGS_ONLY = re.compile(r"^(?:\s*#[^\s#]+)+\s*$")


def _raw_levels(text: str, most: int, limit: int) -> list[str]:
    explicit = [p.strip() for p in re.split(r"(?m)^[ \t]*---[ \t]*$", str(text or "")) if p.strip()]
    if len(explicit) > 1:
        # the writer marked the posts itself (a line holding only ---): each is one post, the first carries the pictures
        # (Wan, 10 Nov 2026: a thread with a continuation, not one post)
        while len(explicit) > most:
            explicit[-2:] = [explicit[-2] + "\n\n" + explicit[-1]]
        return explicit
    paras = [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]
    if len(paras) <= 1:
        return paras
    levels: list[str] = [paras[0]]                 # the hook stands alone on the first level, above the pictures
    for para in paras[1:]:
        if len(levels) > 1 and len(levels[-1]) + 2 + len(para) <= limit:
            levels[-1] += "\n\n" + para
        else:
            levels.append(para)
    while len(levels) > most:
        levels[-2:] = [levels[-2] + "\n\n" + levels[-1]]
    return levels


def has_loose_tags(text: str, most: int = THREAD_LEVELS, limit: int = THREAD_MAX) -> bool:
    """True when a caption would make a post of hashtags alone (the line of tags under the words). Threads refuses such a
    post ("The parameter text is required": it reads a tags-only post as a topic, leaving no text), 11 Nov 2026."""
    return any(_TAGS_ONLY.match(lv) for lv in _raw_levels(text, most, limit)[1:])


def thread_levels(text: str, most: int = THREAD_LEVELS, limit: int = THREAD_MAX) -> list[str]:
    """A caption as the levels of one Threads chain: its paragraphs in order, neighbours joined while they fit one post, at
    most `most` levels (the tail is folded into the last ones). Joined with a blank line, the levels are the caption again,
    which is how a chain already in Zernio is recognised as this post. A caption of one paragraph is one level. A line of
    hashtags alone is never a level of its own: it stays under the words before it (a post of tags alone is refused by
    Threads, 11 Nov 2026: "The parameter text is required")."""
    out: list[str] = []
    for lv in _raw_levels(text, most, limit):
        if out and _TAGS_ONLY.match(lv):
            if len(out[-1]) + 2 + len(lv) <= limit:
                out[-1] += "\n\n" + lv
                continue
            if len(out[-1]) + 1 + len(lv) <= limit:
                out[-1] += " " + lv
                continue
        out.append(lv)
    return out


class Zernio:
    """One Zernio login (one key) and the social accounts connected under it. It answers in Buffer's shape (id, status,
    dueAt, sentAt, text, channelId, externalLink, error) so the publisher's no-double-post check, tally and records are the
    same code for both. A Threads post is a chain (`threadItems`); TikTok takes a video only."""

    def __init__(self, api_key: str, session: Any = None, url: str = ZERNIO_URL, sleep=time.sleep):
        self.key, self.url = api_key, url.rstrip("/")
        self.http = session or requests.Session()
        self.sleep = sleep

    def _call(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        try:
            r = self.http.request(method, f"{self.url}{path}", timeout=90,
                                  headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}, **kw)
        except requests.RequestException as exc:
            raise SendError("transient", f"Zernio unreachable: {exc}") from exc
        if r.status_code == 429 or r.status_code >= 500:
            raise SendError("transient", f"Zernio answered {r.status_code}")
        try:
            body = r.json()
        except ValueError as exc:
            raise SendError("refused", f"Zernio answered {r.status_code} with no JSON") from exc
        if r.status_code >= 400:
            msg = str(body.get("error") or body.get("message") or body)[:400] if isinstance(body, dict) else str(body)[:400]
            raise SendError("refused", f"Zernio refused ({r.status_code}): {msg}")
        return body if isinstance(body, dict) else {}

    @staticmethod
    def shape(post: dict[str, Any], account_id: str = "") -> dict[str, Any]:
        """A Zernio post as the publisher reads a Buffer one, for ONE of its platforms (`account_id`, else its first)."""
        plats = post.get("platforms") or []

        def acc(p: dict[str, Any]) -> str:
            a = p.get("accountId")
            return str(a.get("_id") if isinstance(a, dict) else a or "")
        plat = next((p for p in plats if account_id and acc(p) == account_id), plats[0] if plats else {})
        items = (plat.get("platformSpecificData") or {}).get("threadItems") or []
        text = "\n\n".join(str(i.get("content") or "") for i in items) if items else str(
            plat.get("customContent") or post.get("content") or "")
        raw = str(plat.get("status") or post.get("status") or "")
        status = ZERNIO_STATUS.get(raw, ZERNIO_STATUS.get(str(post.get("status") or ""), "scheduled"))
        out: dict[str, Any] = {"id": post.get("_id"), "status": status, "text": text, "channelId": acc(plat),
                               "dueAt": plat.get("scheduledFor") or post.get("scheduledFor"),
                               "sentAt": plat.get("publishedAt") or post.get("publishedAt")}
        if plat.get("platformPostUrl"):
            out["externalLink"] = plat["platformPostUrl"]
        if status == "error":
            out["error"] = {"message": str(plat.get("errorMessage") or plat.get("error") or post.get("errorMessage")
                                           or "Zernio reported a failure")[:400]}
        return out

    def _create(self, account_id: str, service: str, text: str, media: list[dict[str, Any]], due_at: str | None,
                video: bool = False, vertical: bool = False) -> dict[str, Any]:
        entry: dict[str, Any] = {"platform": service, "accountId": account_id}
        content, data = text, {}
        if service == "threads":
            levels = thread_levels(text)
            if len(levels) > 1:
                content = levels[0]
                data["threadItems"] = [{"content": lv, "mediaItems": media if i == 0 else []} for i, lv in enumerate(levels)]
        elif service == "instagram" and video:
            data["contentType"] = "reels"
        elif service == "facebook" and video and vertical:
            data["contentType"] = "reel"
        if data:
            entry["platformSpecificData"] = data
        body: dict[str, Any] = {"content": content, "timezone": "UTC", "mediaItems": media, "platforms": [entry]}
        if due_at:
            body["scheduledFor"] = due_at
        else:
            body["publishNow"] = True
        if service == "tiktok":
            body["tiktokSettings"] = dict(TIKTOK_SETTINGS)
        got = self._call("POST", "/posts", json=body)
        post = got.get("post") if isinstance(got.get("post"), dict) else got
        if not post.get("_id"):
            raise SendError("refused", f"Zernio gave no post id: {str(got)[:300]}")
        return self.shape(post, account_id)

    def create(self, channel_id: str, service: str, text: str, pictures: list[str], alt: str,
               due_at: str | None) -> dict[str, Any]:
        if service == "tiktok":
            raise SendError("refused", "tiktok: TikTok takes a Motion film only")
        return self._create(channel_id, service, text, [{"type": "image", "url": u} for u in pictures], due_at)

    def create_video(self, channel_id: str, service: str, text: str, video: dict[str, Any],
                     due_at: str | None) -> dict[str, Any]:
        return self._create(channel_id, service, text, [{"type": "video", "url": video["url"]}], due_at, video=True,
                            vertical=bool(video.get("vertical")))

    def get(self, post_id: str, account_id: str = "") -> dict[str, Any]:
        got = self._call("GET", f"/posts/{post_id}")
        return self.shape(got.get("post") if isinstance(got.get("post"), dict) else got, account_id)

    def delete(self, post_id: str) -> dict[str, Any]:
        """DELETE /posts/{id} (Wan, 10 Nov 2026: a scheduled post is pulled back to be edited). A post that is already gone
        is a success: the aim is that it is not in the queue. A post that has been published cannot be deleted, and Zernio
        says so."""
        try:
            return self._call("DELETE", f"/posts/{post_id}")
        except SendError as exc:
            if "(404)" in str(exc) or "not found" in str(exc).lower():
                return {"gone": True}
            raise

    def posts(self, channel_ids: list[str], start: str, end: str) -> list[dict[str, Any]]:
        """Every post of these accounts due in [start, end], any status, in Buffer's shape (one row per account)."""
        want = {str(c) for c in channel_ids}
        out: list[dict[str, Any]] = []
        for page in range(1, 21):
            got = self._call("GET", "/posts", params={"page": page, "limit": 100, "dateFrom": start[:10], "dateTo": end[:10]})
            rows = got.get("posts") or []
            for post in rows:
                for plat in post.get("platforms") or []:
                    a = plat.get("accountId")
                    aid = str(a.get("_id") if isinstance(a, dict) else a or "")
                    if aid in want:
                        out.append(self.shape(post, aid))
            if page >= int((got.get("pagination") or {}).get("pages") or 1) or not rows:
                break
        return out

    def confirm(self, post_id: str, tries: int = 20, every: float = 6.0, account_id: str = "") -> dict[str, Any]:
        """A publish-now is read back until the network settles it (a video takes minutes: unconfirmed is not a failure)."""
        last: dict[str, Any] = {}
        for _ in range(tries):
            last = self.get(post_id, account_id)
            if last.get("status") in ("sent", "error"):
                return last
            self.sleep(every)
        return {**last, "unconfirmed": True}

    def accounts(self) -> list[dict[str, Any]]:
        return self._call("GET", "/accounts").get("accounts") or []

    def analytics(self, from_date: str, to_date: str, pages: int = 20) -> list[dict[str, Any]]:
        """Every post this login published through Zernio in [from_date, to_date] with its figures (GET /v1/analytics,
        `source=late`: posts sent through Zernio only, so a post Buffer sent is never counted twice). Zernio allows a few
        analytics reads a second, so the pages are paced."""
        out: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            got = self._call("GET", "/analytics", params={"source": "late", "fromDate": from_date[:10], "toDate": to_date[:10],
                                                           "limit": 100, "page": page})
            rows = got.get("posts") or []
            out += [r for r in rows if isinstance(r, dict)]
            pg = got.get("pagination") or {}
            last = int(pg.get("pages") or pg.get("totalPages") or 0)
            if not rows or len(rows) < 100 or (last and page >= last):
                break
            self.sleep(0.5)
        return out


class ZernioHub:
    """Wan's Zernio is three logins (Instagram and Threads; LinkedIn and Facebook; TikTok), so three keys. The hub is one
    sender for the publisher: each social account id goes to the login that holds it."""

    def __init__(self, by_account: dict[str, Zernio]):
        self.by_account = dict(by_account)

    def _for(self, account_id: str) -> Zernio:
        client = self.by_account.get(str(account_id))
        if client is None:
            raise SendError("refused", f"no Zernio key is set for the account {account_id}")
        return client

    def create(self, channel_id: str, service: str, text: str, pictures: list[str], alt: str,
               due_at: str | None) -> dict[str, Any]:
        return self._for(channel_id).create(channel_id, service, text, pictures, alt, due_at)

    def create_video(self, channel_id: str, service: str, text: str, video: dict[str, Any],
                     due_at: str | None) -> dict[str, Any]:
        return self._for(channel_id).create_video(channel_id, service, text, video, due_at)

    def posts(self, channel_ids: list[str], start: str, end: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for cid in channel_ids:
            out += self._for(cid).posts([cid], start, end)
        return out

    def analytics(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        """Every login's posts with their figures, each login asked once."""
        out: list[dict[str, Any]] = []
        for client in {id(c): c for c in self.by_account.values()}.values():
            out += client.analytics(from_date, to_date)
        return out

    def delete(self, post_id: str, account_id: str = "") -> dict[str, Any]:
        """Take a post out of Zernio's queue; the login that holds `account_id` does it."""
        return self._for(account_id).delete(post_id)

    def get(self, post_id: str, account_id: str = "") -> dict[str, Any]:
        if account_id:
            return self._for(account_id).get(post_id, account_id)
        last: SendError | None = None
        for client in {id(c): c for c in self.by_account.values()}.values():
            try:
                return client.get(post_id)
            except SendError as exc:           # a post of another login is "not found" here: ask the next one
                last = exc
        raise last or SendError("refused", "no Zernio login is set up")

    def confirm(self, post_id: str, account_id: str = "", **kw: Any) -> dict[str, Any]:
        if account_id:
            return self._for(account_id).confirm(post_id, account_id=account_id, **kw)
        owner = self.get(post_id)                   # which login holds it, and for which account
        return self._for(owner.get("channelId") or "").confirm(post_id, account_id=owner.get("channelId") or "", **kw)


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
        acct = self.account()                   # before the post call: a failure here cannot have posted anything
        try:
            body = self._call("POST", f"/api/v3.1/tools/execute/{LINKEDIN_TOOL}",
                              json={"connected_account_id": acct, "arguments": args})
        except SendError as exc:
            # the post call went out: a timeout or 5xx does not prove it never landed, so never let the publisher retry
            raise SendError("refused", f"LinkedIn refused or unconfirmed: {exc.message}") from exc
        if not body.get("successful"):
            msg = str(body.get("error") or "no reason given")
            raise SendError(classify(msg), f"LinkedIn refused: {msg}")
        data = body.get("data") or {}
        urn = data.get("x_restli_id") or data.get("id") or ""
        if not urn.startswith("urn:li:"):
            # it may have posted: never let the publisher try again on its own
            raise SendError("refused", f"LinkedIn answered without a post id: {str(data)[:300]}")
        return LinkedInResult(urn=urn, url=f"https://www.linkedin.com/feed/update/{urn}/")


    def post_video(self, text: str, video_url: str) -> LinkedInResult:
        """A native video post: LinkedIn takes the public MP4 address and has the video ready (nothing posts yet, so a
        failure here may be tried again), then the post itself goes once and is never retried (it may have landed)."""
        up = self._call("POST", f"/api/v3.1/tools/execute/{LINKEDIN_VIDEO_UPLOAD}",
                        json={"connected_account_id": self.account(), "arguments": {"video_url": video_url}})
        if not up.get("successful"):
            msg = str(up.get("error") or "no reason given")
            raise SendError(classify(msg), f"LinkedIn did not take the video: {msg}")
        urn = _video_urn(up.get("data"))
        if not urn:
            raise SendError("refused", f"LinkedIn answered the video upload without a video id: {str(up.get('data'))[:300]}")
        try:
            body = self._call("POST", f"/api/v3.1/tools/execute/{LINKEDIN_VIDEO_POST}",
                              json={"connected_account_id": self.account(),
                                    "arguments": {"video_urn": urn, "commentary": text, "visibility": "PUBLIC"}})
        except SendError as exc:
            raise SendError("refused", f"LinkedIn refused or unconfirmed: {exc.message}") from exc
        if not body.get("successful"):
            msg = str(body.get("error") or "no reason given")
            raise SendError("refused", f"LinkedIn refused: {msg}")
        post = _share_urn(body.get("data"))
        if not post:
            raise SendError("refused", f"LinkedIn answered without a post id: {str(body.get('data'))[:300]}")
        return LinkedInResult(urn=post, url=f"https://www.linkedin.com/feed/update/{post}/")


# --- Composio For You (LinkedIn over MCP) --------------------------------------------------------------------------
#
# Wan, 30 Sep 2026: the LinkedIn connection lives in Composio's FOR YOU workspace (the one ws.regulab Studio and
# Claude use), not in any Platform project, so a Platform key (COMPOSIO_API_KEY, x-api-key) can never see it. The
# For You side is reached only through its MCP endpoint with the consumer key (COMPOSIO_CONSUMER_KEY, header
# x-consumer-api-key). Its tools are Composio's meta tools, so the picture upload and the post both run inside the
# Composio workbench, exactly as Studio did:
#   call 1  fetch each card by URL and put it through upload_local_file  -> s3keys   (safe to retry: nothing posted)
#   call 2  run_composio_tool(LINKEDIN_CREATE_LINKED_IN_POST)            -> urn      (NEVER retried: may have posted)

MCP_URL = os.environ.get("COMPOSIO_MCP_URL", "https://connect.composio.dev/mcp")
MCP_PROTOCOL = "2025-03-26"
_MARK = "SEMASA_RESULT "

_UPLOAD_CELL = """
import json, base64, os, mimetypes, requests
def _semasa():
    urls = json.loads(base64.b64decode("{urls}").decode())
    os.makedirs("/home/user/semasa", exist_ok=True)
    out = []
    for i, u in enumerate(urls, 1):
        r = requests.get(u, timeout=60)
        ct = (r.headers.get("content-type") or "").split(";")[0].strip()
        if r.status_code != 200 or not ct.startswith("image/"):
            why = f"picture {{i}} answered {{r.status_code}} {{ct or 'no type'}}: {{u}}"
            return {{"ok": False, "kind": "refused", "message": why}}
        name = f"slide-{{i:02d}}" + (mimetypes.guess_extension(ct) or ".jpg")
        path = "/home/user/semasa/" + name
        with open(path, "wb") as fh:
            fh.write(r.content)
        res, err = upload_local_file(path)
        if err:
            return {{"ok": False, "kind": "transient", "message": f"picture {{i}} upload failed: {{err}}"}}
        key = (res or {{}}).get("s3key") or ((res or {{}}).get("data") or {{}}).get("s3key")
        if not key:
            return {{"ok": False, "kind": "transient", "message": f"picture {{i}} upload gave no s3key: {{str(res)[:200]}}"}}
        out.append({{"name": name, "mimetype": ct, "s3key": key}})
    return {{"ok": True, "images": out}}
try:
    _r = _semasa()
except Exception as _e:
    _r = {{"ok": False, "kind": "transient", "message": f"{{type(_e).__name__}}: {{_e}}"}}
print("{mark}" + json.dumps(_r))
"""

_POST_CELL = """
import json, base64
_args = json.loads(base64.b64decode("{args}").decode())
try:
    _res, _err = run_composio_tool("{tool}", _args{account})
    _r = {{"err": str(_err) if _err else "", "res": _res}}
except Exception as _e:
    _r = {{"err": f"{{type(_e).__name__}}: {{_e}}", "res": None}}
print("{mark}" + json.dumps(_r, default=str))
"""


_VIDEO_URN = re.compile(r"urn:li:video:[A-Za-z0-9_-]+")


def _video_urn(obj: Any) -> str:
    """The urn:li:video an upload answered with, wherever the answer nested it."""
    import json
    m = _VIDEO_URN.search(json.dumps(obj, default=str))
    return m.group(0) if m else ""


def _share_urn(obj: Any) -> str:
    """The post's urn in a video post's answer: the first urn that is not the video's own."""
    import json
    for m in re.finditer(r"urn:li:[A-Za-z]+:[A-Za-z0-9_-]+", json.dumps(obj, default=str)):
        if ":video:" not in m.group(0):
            return m.group(0)
    return ""


def _b64(obj: Any) -> str:
    import base64
    import json
    return base64.b64encode(json.dumps(obj, ensure_ascii=False).encode()).decode()


def _find_urn(obj: Any) -> str:
    """The post's urn wherever the workbench nested it (x_restli_id first, then any id that is a urn)."""
    if isinstance(obj, dict):
        for k in ("x_restli_id", "id"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith("urn:li:"):
                return v
        for v in obj.values():
            found = _find_urn(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_urn(v)
            if found:
                return found
    return ""


class ComposioMCP:
    """The connection to Composio For You's MCP endpoint with the consumer key: the JSON-RPC wire, the session, the meta
    tool call and the workbench cell. LinkedInMCP (below) and the three source readers (foryou.py) are built on it, so
    there is one place that knows how the endpoint answers."""

    def __init__(self, consumer_key: str, session: Any = None, url: str = MCP_URL):
        self.key, self.url = consumer_key, url
        self.http = session or requests.Session()
        self.sid: str | None = None
        self.n = 0

    # the wire -------------------------------------------------------------------------------------------------------
    def _rpc(self, method: str, params: dict[str, Any] | None = None, note: bool = False) -> dict[str, Any]:
        import json
        headers = {"x-consumer-api-key": self.key, "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": MCP_PROTOCOL}
        if self.sid:
            headers["Mcp-Session-Id"] = self.sid
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not note:
            self.n += 1
            msg["id"] = self.n
        try:
            r = self.http.post(self.url, json=msg, headers=headers, timeout=240)
        except requests.RequestException as exc:
            raise SendError("transient", f"Composio MCP unreachable: {exc}") from exc
        sid = (r.headers or {}).get("Mcp-Session-Id") or (r.headers or {}).get("mcp-session-id")
        if sid:
            self.sid = sid
        if r.status_code in (401, 403):
            raise SendError("refused", f"Composio MCP answered {r.status_code}: check the COMPOSIO_CONSUMER_KEY secret")
        if r.status_code == 429 or r.status_code >= 500:
            raise SendError("transient", f"Composio MCP answered {r.status_code}")
        if note:
            return {}
        if r.status_code >= 400:
            raise SendError("refused", f"Composio MCP answered {r.status_code}: {str(getattr(r, 'text', ''))[:300]}")
        ctype = ((r.headers or {}).get("content-type") or (r.headers or {}).get("Content-Type") or "").lower()
        bodies: list[Any] = []
        # Decode the BYTES as UTF-8. requests guesses Latin-1 for a text/event-stream with no charset, which turns the
        # ✅ in the workbench's own upload message (E2 9C 85) into a string holding U+0085, and str.splitlines() treats
        # U+0085 as a line break: the answer's data line was cut in half, no JSON parsed, and the probe reported "no
        # answer for request 3" while the answer, id 3 included, was sitting in the body (run 36655669614).
        raw = getattr(r, "content", b"") or b""
        text = raw.decode("utf-8", errors="replace") if raw else str(getattr(r, "text", ""))
        if "text/event-stream" in ctype:
            for line in text.split("\n"):
                line = line.rstrip("\r")
                if line.startswith("data:"):
                    try:
                        bodies.append(json.loads(line[5:].strip()))
                    except ValueError:
                        continue
        else:
            try:
                bodies.append(r.json())
            except ValueError as exc:
                raise SendError("refused", f"Composio MCP answered {r.status_code} with no JSON") from exc
        flat: list[Any] = []
        for b in bodies:
            flat.extend(b if isinstance(b, list) else [b])       # a JSON-RPC batch is a list of answers
        for b in flat:
            if not isinstance(b, dict):
                continue
            mine = str(b.get("id")) == str(msg["id"])
            # one request is in flight, so an error with no id at all (a server that could not read the request far
            # enough to copy its id back) is the answer to it
            orphan_error = b.get("id") is None and b.get("error")
            if mine or orphan_error:
                if b.get("error"):
                    raise SendError("refused", f"Composio MCP {method}: {_message(b)}")
                return b.get("result") or {}
        seen = text[:300].replace("\n", " ")
        raise SendError("transient", f"Composio MCP {method}: no answer for request {msg['id']} "
                                     f"(HTTP {r.status_code}, {ctype or 'no content-type'}, body starts: {seen!r})")

    @staticmethod
    def _twice(fn: Any) -> Any:
        """One more try, 2 seconds later, when Composio's gateway says 5xx/429 or does not answer. ONLY for calls that
        cannot have posted anything: opening the session and listing connections (a 502 from connect.composio.dev
        failed a probe run at exactly that step, run 36655570023). The post call never goes through here."""
        try:
            return fn()
        except SendError as exc:
            if exc.kind != "transient":
                raise
            time.sleep(2)
            return fn()

    def _open(self) -> None:
        if self.sid is not None or self.n:
            return
        self._twice(lambda: self._rpc("initialize", {"protocolVersion": MCP_PROTOCOL, "capabilities": {},
                                                     "clientInfo": {"name": "semasa-publisher", "version": "1"}}))
        self._rpc("notifications/initialized", note=True)

    def _tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """One meta tool call; returns the JSON Composio put in the text content."""
        import json
        self._open()
        res = self._rpc("tools/call", {"name": name, "arguments": arguments})
        text = "".join(c.get("text", "") for c in res.get("content") or [] if isinstance(c, dict))
        try:
            body = json.loads(text) if text else {}
        except ValueError:
            body = {"raw": text}
        if res.get("isError"):
            raise SendError(classify(text), f"Composio {name}: {text[:300]}")
        return body if isinstance(body, dict) else {"raw": body}

    def _cell(self, code: str, thought: str) -> dict[str, Any]:
        import json
        body = self._tool("COMPOSIO_REMOTE_WORKBENCH", {"code_to_execute": code, "thought": thought})
        data = body.get("data") or {}
        for line in str(data.get("stdout") or "").splitlines():
            if line.startswith(_MARK):
                return json.loads(line[len(_MARK):])
        raise SendError("transient", f"workbench gave no result: {str(data.get('error') or data.get('stderr') or body)[:300]}")



class LinkedInMCP(ComposioMCP):
    """LinkedIn through Composio For You's MCP endpoint and the consumer key. Same face as LinkedIn above (post,
    account), so the publisher does not care which road it is given."""

    def __init__(self, consumer_key: str, author: str, session: Any = None, url: str = MCP_URL,
                 account_id: str | None = None):
        super().__init__(consumer_key, session=session, url=url)
        self.author = author
        self.account_id = account_id

    # the face -------------------------------------------------------------------------------------------------------
    def account(self) -> str:
        if self.account_id:
            return self.account_id
        body = self._twice(lambda: self._tool("COMPOSIO_MANAGE_CONNECTIONS",
                                              {"toolkits": [{"name": "linkedin", "action": "list"}]}))
        accts = (((body.get("data") or {}).get("results") or {}).get("linkedin") or {}).get("accounts") or []
        live = [a for a in accts if str(a.get("status", "")).lower() == "active"]
        if len(live) != 1:
            raise SendError("refused", f"Composio For You: expected exactly 1 active LinkedIn connection, found {len(live)}")
        who = (live[0].get("user_info") or {}).get("sub")
        if who and not self.author.endswith(":" + who):
            raise SendError("refused", f"Composio For You: the LinkedIn connection is {who}, not {self.author}")
        self.account_id = live[0]["id"]
        return self.account_id

    def upload(self, urls: list[str]) -> list[dict[str, str]]:
        r = self._cell(_UPLOAD_CELL.format(urls=_b64(urls), mark=_MARK), "Semasa: upload LinkedIn card pictures")
        if not r.get("ok"):
            raise SendError(r.get("kind") or "transient", str(r.get("message") or "picture upload failed"))
        return r["images"]

    def probe_upload(self) -> str:
        """For the senders probe: a 1-pixel JPEG made inside the workbench goes through upload_local_file. Nothing posts."""
        code = (
            "import json\nfrom PIL import Image\n"
            "try:\n"
            "    Image.new('RGB', (1, 1), (255, 255, 255)).save('/home/user/semasa-probe.jpg', 'JPEG')\n"
            "    _res, _err = upload_local_file('/home/user/semasa-probe.jpg')\n"
            "    _k = (_res or {}).get('s3key') or ((_res or {}).get('data') or {}).get('s3key')\n"
            "    _r = {'ok': bool(_k) and not _err, 'key': _k or '', 'message': str(_err or '')}\n"
            "except Exception as _e:\n"
            "    _r = {'ok': False, 'key': '', 'message': f'{type(_e).__name__}: {_e}'}\n"
            f"print({_MARK!r} + json.dumps(_r))\n")
        r = self._cell(code, "Semasa: probe the picture upload (nothing is posted)")
        if not r.get("ok"):
            raise SendError("transient", f"probe picture upload failed: {r.get('message')}")
        return r["key"]

    def post(self, text: str, pictures: list[str]) -> LinkedInResult:
        acct = self.account()
        images = self.upload(pictures[:20]) if pictures else []
        args: dict[str, Any] = {"author": self.author, "commentary": text, "visibility": "PUBLIC"}
        if images:
            args["images"] = images
        code = _POST_CELL.format(args=_b64(args), tool=LINKEDIN_TOOL, account=f", account={acct!r}", mark=_MARK)
        try:
            r = self._cell(code, "Semasa: post to LinkedIn")
        except SendError as exc:
            # the post call went out: whatever happened, it may be on LinkedIn, so never let the publisher retry
            raise SendError("refused", f"LinkedIn refused or unconfirmed: {exc.message}") from exc
        res = r.get("res")
        if r.get("err") or (isinstance(res, dict) and res.get("successful") is False):
            msg = r.get("err") or (res or {}).get("error") or "no reason given"
            raise SendError("refused", f"LinkedIn refused: {msg}")
        urn = _find_urn(res)
        if not urn:
            raise SendError("refused", f"LinkedIn answered without a post id: {str(res)[:300]}")
        return LinkedInResult(urn=urn, url=f"https://www.linkedin.com/feed/update/{urn}/")

    def post_video(self, text: str, video_url: str) -> LinkedInResult:
        """The video route of `post` (see LinkedIn.post_video): upload first, which may be tried again, then the post once."""
        acct = self.account()
        account = f", account={acct!r}"
        up = self._cell(_POST_CELL.format(args=_b64({"video_url": video_url}), tool=LINKEDIN_VIDEO_UPLOAD, account=account,
                                          mark=_MARK), "Semasa: hand LinkedIn the video")
        res = up.get("res")
        if up.get("err") or (isinstance(res, dict) and res.get("successful") is False):
            msg = up.get("err") or (res or {}).get("error") or "no reason given"
            raise SendError(classify(str(msg)), f"LinkedIn did not take the video: {msg}")
        urn = _video_urn(res)
        if not urn:
            raise SendError("refused", f"LinkedIn answered the video upload without a video id: {str(res)[:300]}")
        args = {"video_urn": urn, "commentary": text, "visibility": "PUBLIC"}
        try:
            r = self._cell(_POST_CELL.format(args=_b64(args), tool=LINKEDIN_VIDEO_POST, account=account, mark=_MARK),
                           "Semasa: post the video to LinkedIn")
        except SendError as exc:
            raise SendError("refused", f"LinkedIn refused or unconfirmed: {exc.message}") from exc
        res = r.get("res")
        if r.get("err") or (isinstance(res, dict) and res.get("successful") is False):
            msg = r.get("err") or (res or {}).get("error") or "no reason given"
            raise SendError("refused", f"LinkedIn refused: {msg}")
        post = _share_urn(res)
        if not post:
            raise SendError("refused", f"LinkedIn answered without a post id: {str(res)[:300]}")
        return LinkedInResult(urn=post, url=f"https://www.linkedin.com/feed/update/{post}/")
