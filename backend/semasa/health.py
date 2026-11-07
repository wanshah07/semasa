"""Health report (Wan, 7 Nov 2026: "check if can send notification email for any update or problem but you must fix them
automatically and send the report"). `python -m semasa.health`, every 6 hours (health.yml).

Each run looks at the whole system, puts right what is safe to put right by itself, and e-mails Wan a report through the same
Gmail connection the invoices use (billing.GmailMCP via Composio):

  * when there is a problem it has not reported yet (the set of problems changed since the last e-mail), and
  * once a day at the morning run (SUMMARY_HOUR_UTC), problems or not, so silence never means "the report broke".

WHAT IT FIXES BY ITSELF (only what cannot do harm):
  * a publisher error left by a bug that is fixed in the code (KNOWN_FIXED): the channel's error is cleared so the publisher
    tries again. The publisher's own rules still hold: an approved post only, never before its slot, and a slot long past is
    "overdue" for Wan to move, never sent late;
  * an idea that failed because the writer did not answer (a time-out or a gateway hiccup, TRANSIENT_IDEA), at most
    MAX_IDEA_RETRIES a run, written in the last IDEA_RETRY_DAYS and tried fewer than 3 times: back to `new`, so the worker writes
    it again. An idea the writer judged no fit is a decision, never retried.

WHAT IT ONLY REPORTS (it needs Wan, or an account outside Semasa): a workflow that failed, an AI gateway that is down or refusing
its key, Gemini keys that all fail, the ChatGPT login about to expire or failing, a LinkedIn account LinkedIn has restricted,
the Gmail connection itself, a billing e-mail that failed.

It writes settings.health_state (the last report, for the page) and one semasa_log line a run. It never sends anything but the
report, and the report goes only to Wan's own address.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from . import billing, db
from .log import get_logger

log = get_logger("semasa.health")

STATE_KEY = "health_state"
SUMMARY_HOUR_UTC = 0                 # the run between 00:00 and 05:59 UTC (08:00-13:59 MYT) sends the daily summary
LOOKBACK_HOURS = 24
IDEA_RETRY_DAYS = 3
MAX_IDEA_RETRIES = 10
KNOWN_FIXED = [
    # (what Buffer or LinkedIn said, the fix): an error that a code change has removed the cause of
    (re.compile(r"thumbnailUrl is not supported", re.I), "Buffer refused the film's cover picture; the cover is no longer sent"),
]
TRANSIENT_IDEA = re.compile(r"did not answer|timed? ?out|temporarily|try again|\b50[234]\b|connection (reset|error|aborted)",
                            re.I)
RESTRICTED = re.compile(r"RESTRICTED_MEMBER|AUTHENTICATION_FAILED|Member is restricted", re.I)
URL = re.compile(r"https?://\S+")              # a run's address changes every run: the fingerprint ignores it


def _parse(stamp: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _rows(store: Any, table: str, build: Any) -> list[dict[str, Any]]:
    try:
        return build(store.table(table)).execute().data or []
    except Exception as exc:  # noqa: BLE001 - one unreadable table is a finding, never a crash
        log.info("%s not read (%s)", table, str(exc)[:120])
        return []


def live_posts(store: Any) -> list[dict[str, Any]]:
    """Approved and scheduled posts: the only ones the publisher still sends."""
    return _rows(store, db.POSTS,
                 lambda q: q.select("id,date,slot,stream,status,errors").in_("status", ["approved", "scheduled"]))


def problem(area: str, what: str, todo: str = "") -> dict[str, str]:
    return {"area": area, "what": " ".join(str(what).split())[:400], "todo": todo}


# ---- the fixes ------------------------------------------------------------------------------------------------------------

def fix_known_publisher_errors(store: Any) -> list[str]:
    """Clears a channel error whose cause is fixed in the code, so the publisher tries that channel again. Returns lines."""
    done = []
    rows = live_posts(store)
    for p in rows:
        errors = dict(p.get("errors") or {})
        cleared = []
        for ch, err in list(errors.items()):
            if not isinstance(err, dict):
                continue
            for pattern, why in KNOWN_FIXED:
                if pattern.search(str(err.get("message") or "")):
                    errors.pop(ch)
                    cleared.append((ch, why))
                    break
        if not cleared:
            continue
        if "at" in errors and not any(isinstance(v, dict) for k, v in errors.items() if k not in ("at", "scan")):
            errors.pop("at")
        try:
            store.table(db.POSTS).update({"errors": errors}).eq("id", p["id"]).execute()
        except Exception as exc:  # noqa: BLE001
            log.warning("post %s: error not cleared (%s)", p["id"], str(exc)[:120])
            continue
        for ch, why in cleared:
            done.append(f"Post {p.get('date') or ''} {p.get('slot') or ''} ({ch}): {why}; it will be tried again at its slot")
    return done


def retry_transient_ideas(store: Any, now: datetime) -> list[str]:
    """Ideas that failed only because the writer did not answer go back to the queue (at most MAX_IDEA_RETRIES a run)."""
    since = (now - timedelta(days=IDEA_RETRY_DAYS)).isoformat()
    rows = _rows(store, db.IDEAS, lambda q: q.select("id,source_title,error,attempts,updated_at").eq("status", "error")
                 .gte("updated_at", since).order("updated_at", desc=True).limit(200))
    done = []
    for r in rows:
        if len(done) >= MAX_IDEA_RETRIES:
            break
        if not TRANSIENT_IDEA.search(str(r.get("error") or "")) or int(r.get("attempts") or 0) >= 3:
            continue
        try:
            hit = (store.table(db.IDEAS).update({"status": "new", "error": None}).eq("id", r["id"]).eq("status", "error")
                   .execute().data)
        except Exception as exc:  # noqa: BLE001
            log.warning("idea %s not requeued (%s)", r["id"], str(exc)[:120])
            continue
        if hit:
            done.append(f"Idea \"{str(r.get('source_title') or '')[:70]}\" was written again (the writer had not answered)")
    return done


# ---- what it reports ------------------------------------------------------------------------------------------------------

def check_workflows(now: datetime, session: Any = None) -> list[dict[str, str]]:
    """Workflow runs of this repository that failed in the last LOOKBACK_HOURS (GitHub's own API, the run's GITHUB_TOKEN)."""
    repo, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", "")
    if not repo or not token:
        return []
    since = (now - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    s = session or requests
    try:
        r = s.get(f"https://api.github.com/repos/{repo}/actions/runs", params={"created": f">={since}", "per_page": 100},
                  headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, timeout=30)
        runs = (r.json() or {}).get("workflow_runs") or [] if r.status_code == 200 else []
    except Exception as exc:  # noqa: BLE001
        return [problem("GitHub", f"the workflow runs could not be read ({type(exc).__name__})")]
    bad: dict[str, list[str]] = {}
    for run in runs:
        if run.get("conclusion") in ("failure", "timed_out", "startup_failure"):
            bad.setdefault(str(run.get("name") or "?"), []).append(str(run.get("html_url") or ""))
    return [problem("GitHub", f"{name}: {len(urls)} run(s) failed in 24 h. Latest: {urls[0]}",
                    "Open the run's log; a code fix is needed if it fails again.") for name, urls in sorted(bad.items())]


def check_gateways(store: Any) -> list[dict[str, str]]:
    out = []
    for r in _rows(store, db.API_STATUS, lambda q: q.select("*")):
        name = r.get("name") or r.get("slug")
        if r.get("key_set") is False:
            continue
        if r.get("key_ok") is False:
            out.append(problem("AI", f"{name}: the key was refused", "Renew the key in Tetapan AI (Technology → API)."))
        elif not r.get("reachable"):
            out.append(problem("AI", f"{name}: not reachable ({str(r.get('error') or '')[:160]})"))
        elif r.get("role") not in ("image",) and r.get("chat_ok") is False:
            out.append(problem("AI", f"{name}: listed its models but its model {r.get('model')} did not answer "
                                     f"({str(r.get('error') or '')[:160]})", "The AI team uses the next robot meanwhile."))
    return out


def check_gemini(store: Any) -> list[dict[str, str]]:
    rows = _rows(store, "semasa_gemini_keys", lambda q: q.select("label,enabled,status,last_error"))
    keys = [k for k in rows if k.get("enabled")]
    if keys and all(k.get("status") in ("bad", "limited") for k in keys):
        return [problem("AI", f"every Gemini key is refused or used up ({', '.join(str(k.get('label')) for k in keys)})",
                        "Add a new Google AI Studio key on the API page.")]
    return []


def check_chatgpt(store: Any, now: datetime) -> list[dict[str, str]]:
    rows = _rows(store, "semasa_chatgpt_auth", lambda q: q.select("enabled,access_expires_at,last_error,last_error_at"))
    out = []
    for r in rows:
        if not r.get("enabled"):
            continue
        end = _parse(r.get("access_expires_at"))
        if end and end - now < timedelta(days=2):
            out.append(problem("AI", f"the ChatGPT login ends {end.date().isoformat()}", "Log in again from the Motion card."))
        err_at = _parse(r.get("last_error_at"))
        if r.get("last_error") and err_at and now - err_at < timedelta(hours=LOOKBACK_HOURS):
            out.append(problem("AI", f"ChatGPT login: {str(r['last_error'])[:200]}"))
    return out


def check_publisher(store: Any) -> list[dict[str, str]]:
    rows = live_posts(store)
    linkedin_locked, out = 0, []
    for p in rows:
        for ch, err in (p.get("errors") or {}).items():
            if not isinstance(err, dict):
                continue
            msg = str(err.get("message") or "")
            if RESTRICTED.search(msg):
                linkedin_locked += 1
                continue
            out.append(problem("Publishing", f"{p.get('date') or ''} {p.get('slot') or ''} on {ch}: {msg[:220]}",
                               "Edit the post or move it to a new slot to send it again."))
    if linkedin_locked:
        out.insert(0, problem("Publishing", f"LinkedIn refuses {linkedin_locked} post(s): the account is restricted or its "
                                            "login failed (LinkedIn's own answer, not Semasa's)",
                              "Check your LinkedIn account, then reconnect LinkedIn in Composio."))
    return out[:15]


def check_billing(store: Any, now: datetime) -> list[dict[str, str]]:
    since = (now - timedelta(hours=LOOKBACK_HOURS)).isoformat()
    out = [problem("Billing", f"an e-mail to {r.get('to_email')} failed: {str(r.get('error') or '')[:200]}",
                   "Open the document in Bil and press Send again once the cause is fixed.")
           for r in _rows(store, "semasa_billing_outbox", lambda q: q.select("to_email,error,status,updated_at")
                          .eq("status", "error").gte("updated_at", since))]
    return out


def check_gmail(sender: Any) -> list[dict[str, str]]:
    """The one Gmail connection every business sends from: listed, never used to send here (except the report itself)."""
    if sender is None:
        return [problem("Billing", "no Gmail route: COMPOSIO_CONSUMER_KEY is not set in the repository secrets")]
    try:
        sender.account()
        return []
    except Exception as exc:  # noqa: BLE001
        return [problem("Billing", f"the Gmail connection did not answer: {str(getattr(exc, 'message', exc))[:200]}",
                        "Reconnect Gmail in Composio; quotations and invoices cannot be e-mailed until then.")]


# ---- the report -----------------------------------------------------------------------------------------------------------

def fingerprint(problems: list[dict[str, str]]) -> str:
    keys = sorted(p["area"] + "|" + URL.sub("", p["what"])[:120] for p in problems)
    return hashlib.sha256(json.dumps(keys).encode()).hexdigest()[:16]


def should_send(problems: list[dict[str, str]], fixed: list[str], state: dict[str, Any], now: datetime) -> str:
    """"" (no e-mail), "problem" (something new to say) or "summary" (the daily one)."""
    if (problems or fixed) and fingerprint(problems) != state.get("emailed_fingerprint"):
        return "problem"
    last = _parse(state.get("summary_at"))
    if now.hour // 6 == SUMMARY_HOUR_UTC // 6 and (last is None or last.date() < now.date()):
        return "summary"
    return ""


def render(problems: list[dict[str, str]], fixed: list[str], now: datetime, kind: str) -> tuple[str, str]:
    myt = (now + timedelta(hours=8)).strftime("%d/%m/%Y %H:%M")
    head = (f"Semasa: {len(problems)} masalah, {len(fixed)} dibaiki sendiri" if problems or fixed
            else "Semasa: semua berjalan baik")
    subject = f"{head} ({myt} MYT)" + (" · ringkasan harian" if kind == "summary" else "")
    esc = html.escape
    parts = [f"<p>Laporan kesihatan Semasa, {esc(myt)} MYT.</p>"]
    if fixed:
        parts.append("<h3>Dibaiki sendiri</h3><ul>" + "".join(f"<li>{esc(x)}</li>" for x in fixed) + "</ul>")
    if problems:
        parts.append("<h3>Perlu perhatian anda</h3><ul>" + "".join(
            f"<li><b>{esc(p['area'])}</b>: {esc(p['what'])}" + (f"<br><i>{esc(p['todo'])}</i>" if p.get("todo") else "") + "</li>"
            for p in problems) + "</ul>")
    if not problems and not fixed:
        parts.append("<p>Tiada masalah ditemui: aliran kerja, gerbang AI, penerbit, bil dan Gmail semuanya baik.</p>")
    parts.append("<p style=\"color:#888;font-size:12px\">Dihantar oleh Semasa (laporan kesihatan, setiap 6 jam). "
                 "Masalah yang sama "
                 "tidak dihantar dua kali; ringkasan dihantar sekali sehari.</p>")
    return subject, "\n".join(parts)


def recipient(settings: dict[str, Any]) -> str:
    return (os.environ.get("HEALTH_EMAIL") or str((settings.get("company") or {}).get("email") or "")).strip()


def load_state(store: Any) -> dict[str, Any]:
    rows = _rows(store, db.SETTINGS, lambda q: q.select("value").eq("key", STATE_KEY))
    return (rows[0].get("value") or {}) if rows else {}


def save_state(store: Any, state: dict[str, Any]) -> None:
    try:
        store.table(db.SETTINGS).upsert({"key": STATE_KEY, "value": state}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("health state not saved (%s)", str(exc)[:120])


def run(store: Any, now: datetime | None = None, sender: Any = None, session: Any = None, fix: bool = True) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    settings = billing.settings_for({"business_id": "wsregulab"}, billing.load_businesses(store), billing.load_settings(store))
    sender = sender if sender is not None else billing.make_sender(settings)
    fixed = (fix_known_publisher_errors(store) + retry_transient_ideas(store, now)) if fix else []
    problems = (check_workflows(now, session) + check_gateways(store) + check_gemini(store) + check_chatgpt(store, now)
                + check_publisher(store) + check_billing(store, now) + check_gmail(sender))
    state = load_state(store)
    kind = should_send(problems, fixed, state, now)
    sent = ""
    to = recipient(settings)
    if kind and sender is not None and to:
        subject, body = render(problems, fixed, now, kind)
        try:
            sender.send(to=to, cc=[], subject=subject, html=body, attachment=None)
            sent = to
            state["emailed_fingerprint"] = fingerprint(problems)
            if kind == "summary":
                state["summary_at"] = now.isoformat()
        except Exception as exc:  # noqa: BLE001 - the report is still kept below and shown on the page
            log.warning("the health report was not e-mailed (%s)", str(getattr(exc, "message", exc))[:200])
            problems.append(problem("Billing", f"the health report itself could not be e-mailed: {str(exc)[:160]}"))
    state.update({"at": now.isoformat(), "problems": problems, "fixed": fixed, "emailed": sent, "kind": kind})
    save_state(store, state)
    try:
        db.log_event(store, "warn" if problems else "info", "system", "health_report",
                     f"Laporan kesihatan: {len(problems)} masalah, {len(fixed)} dibaiki" + (f", e-mel ke {sent}" if sent else ""),
                     detail={"problems": problems[:20], "fixed": fixed[:20]})
    except Exception as exc:  # noqa: BLE001
        log.info("log line not written (%s)", str(exc)[:120])
    return {"problems": len(problems), "fixed": len(fixed), "emailed": bool(sent), "kind": kind}


def main() -> int:
    out = run(db.client())
    print(f"Health: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
