"""Every Motion storyboard is shown and approved before anything else is made (Wan, 7 Nov 2026: "make sure all storyboard
appear and approve before proceed for motion creation").

The worker writes the storyboard, saves it on the row (`storyboard`, supabase/071) and sets the film to 'review'. Nothing is
drawn, rendered or spent after that point until Wan approves it in the Motion tab or on Telegram, which stamps
`storyboard_approved_at` and sets the film 'pending' again. The worker then makes the film from EXACTLY the saved storyboard.

The database holds the line as well (071's guard): a film whose storyboard was never approved cannot become 'done'.

Before 071 is applied the 'review' status and the columns do not exist. The film is then put back in the queue ('waiting')
with a note saying so: it is never made without an approval, and nothing past the storyboard has been spent.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

TABLE = "semasa_motions"
REVIEW = "review"
KINDS = ("explainer", "showcase", "story")
NOT_APPLIED = ("Storyboard approval needs supabase/071_motion_storyboard_review.sql applied. Nothing was drawn or rendered; "
               "press Mula again once it is applied.")


class StoryboardNeedsFix(Exception):
    """An approved storyboard (usually one Wan edited) that no longer passes the film's checks: it goes back for review."""


def approved(row: dict[str, Any], kind: str) -> dict[str, Any] | None:
    """The saved storyboard when Wan approved it for this kind of film, else None (write one and ask)."""
    sb = row.get("storyboard")
    if not row.get("storyboard_approved_at") or not isinstance(sb, dict) or sb.get("kind") != kind:
        return None
    return sb


def hold(store: Any, row: dict[str, Any], kind: str, body: dict[str, Any], note: str, *, notify: Any = None) -> bool:
    """Save the storyboard, set the film to 'review' and tell Wan on Telegram. True when it is waiting for him; False when 071
    is not applied (the film is put back in the queue instead, with the reason)."""
    if kind not in KINDS:
        raise ValueError(f"unknown film kind {kind!r}")
    saved = {"kind": kind, **body, "note": note, "written_at": datetime.now(UTC).isoformat(timespec="seconds")}
    try:
        store.table(TABLE).update({"status": REVIEW, "storyboard": saved, "storyboard_approved_at": None,
                                   "storyboard_approved_by": None, "error": "", "stage": "storyboard"}) \
            .eq("id", row["id"]).execute()
    except Exception as exc:  # noqa: BLE001 - only a missing column or status is expected here
        log.warning("%s: storyboard not held (%s)", row["id"], str(exc)[:200])
        store.table(TABLE).update({"status": "waiting", "error": NOT_APPLIED}).eq("id", row["id"]).execute()
        return False
    row.update(status=REVIEW, storyboard=saved, storyboard_approved_at=None)
    try:
        (notify or telegram_notify)(store, {**row, "storyboard": saved})
    except Exception as exc:  # noqa: BLE001 - the page shows it either way
        log.info("%s: storyboard not sent to Telegram (%s)", row["id"], str(exc)[:160])
    return True


def send_back(store: Any, row: dict[str, Any], reason: str) -> None:
    """An approved storyboard that fails its checks: back to 'review' with the reason, the approval taken off."""
    store.table(TABLE).update({"status": REVIEW, "storyboard_approved_at": None, "storyboard_approved_by": None,
                               "error": f"Storyboard needs a fix before the film is made: {reason}"[:600],
                               "stage": "storyboard"}).eq("id", row["id"]).execute()


# ---- the storyboard as words (the Telegram message and the page share the same shape) ---------------------------------------

def scenes_of(sb: dict[str, Any]) -> list[dict[str, Any]]:
    """Each scene of a saved storyboard as {label, heading, lines, said, shot}, in order."""
    kind = sb.get("kind")
    if kind == "explainer":
        out = []
        for sc in (sb.get("plan") or {}).get("scenes") or []:
            out.append({"label": sc.get("kicker") or sc.get("role") or sc.get("id") or "", "heading": sc.get("heading") or "",
                        "lines": list(sc.get("lines") or []), "said": sc.get("narration") or "", "shot": sc.get("shot") or ""})
        return out
    body = sb.get("sb") or {}
    if kind == "story":
        return ([{"label": f"{i + 1:02d}", "heading": sc.get("caption") or "", "lines": [], "said": "",
                  "shot": sc.get("prompt") or ""} for i, sc in enumerate(body.get("scenes") or [])]
                + [{"label": "Penutup", "heading": body.get("title") or "", "lines": [body.get("subtitle") or ""], "said": "",
                    "shot": ""}])
    if kind == "showcase":
        head = body.get("headline") or ["", ""]
        return ([{"label": "Intro", "heading": body.get("hook") or "", "lines": [body.get("title") or ""], "said": "",
                  "shot": body.get("background") or ""}]
                + [{"label": f"Produk {i + 1}", "heading": p.get("name") or "", "lines": list(p.get("benefits") or []),
                    "said": "", "shot": ""} for i, p in enumerate(body.get("products") or [])]
                + [{"label": "Penutup", "heading": " · ".join(str(x) for x in head), "lines": [body.get("caption") or ""],
                    "said": "", "shot": ""}])
    return []


def title_of(row: dict[str, Any], sb: dict[str, Any]) -> str:
    if sb.get("kind") == "explainer":
        return str((sb.get("plan") or {}).get("title") or row.get("brief") or "")
    return str((sb.get("sb") or {}).get("title") or row.get("brief") or "")


def telegram_text(row: dict[str, Any], sb: dict[str, Any], limit: int = 3900) -> str:
    kind = {"explainer": "Penerangan", "showcase": "Pameran produk", "story": "Cerita foto"}.get(sb.get("kind"), "")
    parts = [f"🎞 Storyboard untuk diluluskan ({kind})", title_of(row, sb)[:160], ""]
    for sc in scenes_of(sb):
        block = [f"▪️ {sc['label']}: {sc['heading']}".strip()]
        block += [f"   • {x}" for x in sc["lines"] if x]
        if sc["said"]:
            block.append(f"   🔊 {sc['said'][:300]}")
        if sc["shot"]:
            block.append(f"   🖼 {sc['shot'][:200]}")
        parts.append("\n".join(block))
    if sb.get("note"):
        parts += ["", str(sb["note"])[:200]]
    parts += ["", "Gambar dan video hanya dibuat selepas anda luluskan. Untuk ubah perkataan, buka Semasa → Video."]
    text = "\n".join(parts)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def telegram_buttons(motion_id: str, site: str) -> list[list[dict[str, str]]]:
    return [[{"text": "✅ Luluskan storyboard", "callback_data": f"sbok:{motion_id}"}],
            [{"text": "🔁 Tulis semula", "callback_data": f"sbre:{motion_id}"},
             {"text": "✏️ Ubah di Semasa", "url": f"{site.rstrip('/')}/#video"}]]


def telegram_notify(store: Any, row: dict[str, Any], bot: Any = None, link: dict[str, Any] | None = None) -> bool:
    """The storyboard on Telegram with its buttons, remembered as sent (settings.telegram_chat.storyboards_sent) so the
    Telegram worker's own push never sends it twice. False, quietly, when no bot token or no linked account."""
    from . import telegram_bot
    from . import telegram_tools as tt
    from .billing import SITE_URL
    bot = bot or telegram_bot.make_bot()
    link = link or (telegram_bot.link_of(store) if bot else None)
    if not bot or not link:
        return False
    sb = row["storyboard"]
    bot.send(int(link["chat_id"]), telegram_text(row, sb), buttons=telegram_buttons(str(row["id"]), SITE_URL))
    st = tt.chat_state(store)
    sent = [x for x in (st.get("storyboards_sent") or []) if isinstance(x, str)]
    sent.append(sent_key(row["id"], sb))
    tt.save_chat_state(store, {**st, "storyboards_sent": sent[-50:]})
    return True


def sent_key(motion_id: Any, sb: dict[str, Any]) -> str:
    """One storyboard of one film: a rewritten storyboard is a new one, and is sent again."""
    return f"{motion_id}@{(sb or {}).get('written_at') or ''}"


def due(store: Any) -> list[dict[str, Any]]:
    """Films waiting on a storyboard not yet sent to Telegram (the net for a send the motion worker could not make)."""
    from . import telegram_tools as tt
    sent = set(tt.chat_state(store).get("storyboards_sent") or [])
    try:
        rows = store.table(TABLE).select("id,brief,title,status,storyboard").eq("status", REVIEW).execute().data or []
    except Exception as exc:  # noqa: BLE001 - before 071 there is no 'review' to find
        log.info("no storyboards read (%s)", str(exc)[:120])
        return []
    return [r for r in rows if isinstance(r.get("storyboard"), dict) and sent_key(r["id"], r["storyboard"]) not in sent]


DECIDE_WORDS = {
    "ok": "✅ Diluluskan. Semasa mula buat gambar dan video sekarang; saya hantar bila siap.",
    "rewrite": "🔁 Storyboard baharu sedang ditulis. Saya hantar di sini untuk diluluskan.",
    "not_linked": "Akaun Telegram ini tidak disambung.",
    "gone": "Video itu sudah tiada.",
    "no_storyboard": "Tiada storyboard untuk diluluskan.",
}


def decide_words(res: str, action: str) -> str:
    if res == "ok":
        return DECIDE_WORDS["ok" if action == "approve" else "rewrite"]
    if res.startswith("status:"):
        return f"Storyboard ini tidak lagi menunggu kelulusan (status: {res.split(':', 1)[1]})."
    return DECIDE_WORDS.get(res, f"Tidak berjaya: {res}")
