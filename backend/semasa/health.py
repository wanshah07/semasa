"""Health report (Wan, 7 Nov 2026: "check if can send notification email for any update or problem but you must fix them
automatically and send the report"). `python -m semasa.health`, every 6 hours (health.yml).

Each run looks at the whole system, puts right what is safe to put right by itself, and e-mails Wan a short watchdog note
from WS REGULAB's Gmail (info@, billing.GmailMCP via Composio), one line a problem (Wan, 7 Nov 2026, like the Halal
Practitioners Hub watchdog):

  * "Semasa watchdog: needs attention" with PROBLEM: lines when a problem starts,
  * "Semasa watchdog: all working again" with FIXED: lines (and when it started) when it clears, or FIXED BY SEMASA: for
    what it put right itself, and
  * a daily check at the morning run (SUMMARY_HOUR_UTC), problems or not, so silence never means "the watchdog broke".

WHAT IT FIXES BY ITSELF (only what cannot do harm):
  * a publisher error left by a bug that is fixed in the code (KNOWN_FIXED): the channel's error is cleared so the publisher
    tries again. The publisher's own rules still hold: an approved post only, never before its slot, and a slot long past is
    "overdue" for Wan to move, never sent late;
  * an idea that failed because the writer did not answer (a time-out or a gateway hiccup, TRANSIENT_IDEA), at most
    MAX_IDEA_RETRIES a run, written in the last IDEA_RETRY_DAYS and tried fewer than 3 times: back to `new`, so the worker writes
    it again. An idea the writer judged no fit is a decision, never retried.

WHAT IT ONLY REPORTS (it needs Wan, or an account outside Semasa): a workflow that failed, an AI gateway that is down or refusing
its key, Gemini keys that all fail, the ChatGPT login about to expire or failing, a LinkedIn account LinkedIn has restricted,
the Gmail connection itself, a business whose own Gmail is not connected yet, a billing e-mail that failed, the
Telegram bot's webhook and messages it left unanswered. The alerts go to Telegram too once the bot is linked.

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

WORKFLOW_FAILED = ("failure", "timed_out", "startup_failure")
WORKFLOW_PAGES = 3                    # per status, 100 runs a page: far more failures than a day ever has


def check_workflows(now: datetime, session: Any = None) -> list[dict[str, str]]:
    """Workflow runs of this repository that failed in the last LOOKBACK_HOURS (GitHub's own API, the run's GITHUB_TOKEN).

    Asked for the failed runs only (`status` = each failed conclusion), page by page: the newest 100 runs of every kind covered
    about 3.5 hours of this repository's day, not the 24 hours this claims."""
    repo, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", "")
    if not repo or not token:
        return []
    since = (now - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    s = session or requests
    runs: dict[str, dict[str, Any]] = {}
    try:
        for status in WORKFLOW_FAILED:
            for page in range(1, WORKFLOW_PAGES + 1):
                r = s.get(f"https://api.github.com/repos/{repo}/actions/runs",
                          params={"created": f">={since}", "status": status, "per_page": 100, "page": page},
                          headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, timeout=30)
                got = ((r.json() or {}).get("workflow_runs") or []) if r.status_code == 200 else []
                for run in got:
                    runs.setdefault(str(run.get("id") or run.get("html_url") or len(runs)), run)
                if len(got) < 100:
                    break
    except Exception as exc:  # noqa: BLE001
        return [problem("GitHub", f"the workflow runs could not be read ({type(exc).__name__})")]
    bad: dict[str, list[str]] = {}
    for run in runs.values():
        if run.get("conclusion") in WORKFLOW_FAILED and str(run.get("created_at") or since) >= since:
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


def check_business_gmail(businesses: dict[str, dict[str, Any]], ws_email: str, sender_for: Any) -> list[dict[str, str]]:
    """A business with an address of its own (Valorith: muhammad.ridzuan22222@gmail.com) sends from that Gmail once it is
    connected in Composio, and from WS REGULAB's inbox until then. Only listed here, never used to send."""
    if sender_for is None:
        return []
    out = []
    for bid, cfg in sorted((businesses or {}).items()):
        co = (cfg or {}).get("company") or {}
        email, name = str(co.get("email") or "").strip(), str(co.get("name") or bid)
        if not email or email.lower() == ws_email.strip().lower():
            continue
        try:
            got = str(sender_for(email).mailbox() or "")
        except Exception as exc:  # noqa: BLE001
            out.append(problem("Billing", f"{name}'s Gmail could not be checked: {str(getattr(exc, 'message', exc))[:160]}"))
            continue
        if got.lower() != email.lower():
            out.append(problem("Billing", f"{name}'s Gmail ({email}) is not connected in Composio: its quotations and invoices "
                                          f"go out from {got or 'the WS REGULAB inbox'}",
                               f"Connect {email} in Composio (Gmail) so {name}'s mail goes from its own address."))
    return out


def check_telegram(store: Any, now: datetime) -> list[dict[str, str]]:
    """The Telegram bot (telegram_bot.py, supabase/069): Telegram's own word on the webhook, and messages from Wan that no
    run has answered. Silent until the bot has been connected once (settings.telegram_bot)."""
    rows = _rows(store, db.SETTINGS, lambda q: q.select("value").eq("key", "telegram_bot"))
    state = (rows[0].get("value") or {}) if rows else {}
    if not state:
        return []
    out = []
    if not state.get("webhook"):
        out.append(problem("Telegram", "the bot is not connected to Semasa's webhook",
                           "Run the Telegram workflow (Actions → Telegram → Run workflow); check TELEGRAM_BOT_TOKEN."))
    err_at = state.get("last_error_at")
    redeploy = ("Re-run the \"Deploy functions\" workflow (Actions → Deploy functions → Run workflow): it sets the function's "
                "TELEGRAM_WEBHOOK_SECRET from the current bot token and deploys semasa-telegram.")
    if state.get("last_error") and isinstance(err_at, (int, float)) and now.timestamp() - err_at < LOOKBACK_HOURS * 3600:
        refused = re.search(r"\b40[13]\b|forbidden|unauthori", str(state["last_error"]), re.I)
        out.append(problem("Telegram", f"Telegram could not deliver to Semasa: {state['last_error']}",
                           ("The webhook's secret does not match (the bot token changed?). " if refused else "") + redeploy))
    since = (now - timedelta(minutes=30)).isoformat()
    stuck = _rows(store, "semasa_telegram_inbox", lambda q: q.select("id").in_("kind", ["private", "callback"])
                  .in_("status", ["new", "working"]).lt("created_at", since))
    if stuck:
        out.append(problem("Telegram", f"{len(stuck)} message(s) from Wan not answered for 30 minutes",
                           "The Telegram workflow was not woken: check the vault dispatch token and Actions."))
    return out


def as_text(body: str) -> str:
    """The e-mail's lines as plain text, for Telegram."""
    return html.unescape(re.sub(r"<[^>]+>", "", body.replace("</p>", "\n"))).strip()


# ---- the report -----------------------------------------------------------------------------------------------------------

def key_of(p: dict[str, str]) -> str:
    """One problem's identity across runs: a run's address changes every run, so it is left out."""
    return p["area"] + "|" + URL.sub("", p["what"])[:120]


def fingerprint(problems: list[dict[str, str]]) -> str:
    keys = sorted(key_of(p) for p in problems)
    return hashlib.sha256(json.dumps(keys).encode()).hexdigest()[:16]


def stamp(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def changes(problems: list[dict[str, str]], state: dict[str, Any], now: datetime) -> tuple[list, list, dict[str, Any]]:
    """(new problems, cleared problems, the open set to keep). A problem keeps the moment it was first seen ("since")."""
    was = state.get("open") or {}
    now_open: dict[str, Any] = {}
    new = []
    for p in problems:
        k = key_of(p)
        if k in now_open:
            continue
        since = (was.get(k) or {}).get("since") or stamp(now)
        now_open[k] = {"area": p["area"], "what": p["what"], "todo": p.get("todo", ""), "since": since}
        if k not in was:
            new.append({**p, "since": since})
    cleared = [{**v, "key": k} for k, v in was.items() if k not in now_open]
    return new, cleared, now_open


def should_send(problems: list[dict[str, str]], fixed: list[str], state: dict[str, Any], now: datetime) -> str:
    """"" (no e-mail), "attention" (a new problem), "fixed" (a problem cleared, or Semasa fixed something itself) or
    "summary" (the daily one, so silence never means the watchdog broke)."""
    new, cleared, _open = changes(problems, state, now)
    if new:
        return "attention"
    if cleared or fixed:
        return "fixed"
    last = _parse(state.get("summary_at"))
    if now.hour // 6 == SUMMARY_HOUR_UTC // 6 and (last is None or last.date() < now.date()):
        return "summary"
    return ""


def _sentence(*bits: str) -> str:
    return " ".join(b.strip().rstrip(".") + "." for b in bits if b and b.strip())


def render(problems: list[dict[str, str]], fixed: list[str], now: datetime, kind: str,
           state: dict[str, Any] | None = None) -> tuple[str, str]:
    """Short and plain, like a watchdog (Wan, 7 Nov 2026, showing the Halal Practitioners Hub's): one line a problem,
    PROBLEM when it starts, FIXED when it clears with the moment it started."""
    new, cleared, now_open = changes(problems, state or {}, now)
    left = len(now_open)
    if kind == "attention":
        subject = "Semasa watchdog: needs attention"
    elif kind == "fixed":
        subject = "Semasa watchdog: " + (f"fixed, {left} still need attention" if left else "all working again")
    else:
        subject = "Semasa watchdog: daily check, " + (f"{left} need attention" if left else "all working")
    esc = html.escape
    lines = []
    shown = new if kind == "attention" else (list(now_open.values()) if kind == "summary" else [])
    for p in shown:
        head = "PROBLEM" if kind == "attention" else f"PROBLEM (since {p['since']})"
        lines.append(f"{head}: " + _sentence(f"{p['area']}: {p['what']}", p.get("todo", "")))
    for c in cleared:
        lines.append(f"FIXED: {c['area']} is working again (problem started {c['since']}). It was: " + _sentence(c["what"]))
    for x in fixed:
        lines.append("FIXED BY SEMASA: " + _sentence(x))
    if kind == "attention" and left > len(new):
        lines.append(f"Still open from before: {left - len(new)}.")
    if kind == "summary" and not left:
        lines.append("All working: workflows, AI gateways, Gemini, ChatGPT, publisher, billing and Gmail.")
    lines.append("Semasa → Log shows every check.")
    return subject, "\n".join(f"<p>{esc(x)}</p>" for x in lines)


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


def run(store: Any, now: datetime | None = None, sender: Any = None, session: Any = None, fix: bool = True,
        sender_for: Any = None, notify_telegram: bool = True) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    businesses = billing.load_businesses(store)
    settings = billing.settings_for({"business_id": "wsregulab"}, businesses, billing.load_settings(store))
    if sender is None:
        sender, sender_for = billing.make_senders(settings)
    ws_email = str((settings.get("company") or {}).get("email") or "")
    fixed = (fix_known_publisher_errors(store) + retry_transient_ideas(store, now)) if fix else []
    problems = (check_workflows(now, session) + check_gateways(store) + check_gemini(store) + check_chatgpt(store, now)
                + check_publisher(store) + check_billing(store, now) + check_gmail(sender)
                + check_business_gmail(businesses, ws_email, sender_for) + check_telegram(store, now))
    state = load_state(store)
    kind = should_send(problems, fixed, state, now)
    sent = ""
    to = recipient(settings)
    _new, _cleared, now_open = changes(problems, state, now)
    # rendered ONCE, against the open set as it was before this run, so the e-mail and Telegram carry the same new and
    # cleared lines (rendering Telegram's copy after state["open"] moved on left it with nothing new and nothing cleared)
    subject, body = render(problems, fixed, now, kind, state) if kind else ("", "")
    mail_error = ""
    if kind and sender is not None and to:
        try:
            sender.send(to=to, cc=[], subject=subject, html=body, attachment=None)
            sent = to
        except Exception as exc:  # noqa: BLE001 - the report is still kept below and shown on the page
            mail_error = str(exc)[:160]
            log.warning("the health report was not e-mailed (%s)", str(getattr(exc, "message", exc))[:200])
            problems.append(problem("Billing", f"the health report itself could not be e-mailed: {mail_error}"))
    told = False
    if kind in ("attention", "fixed") and notify_telegram:
        from . import telegram_bot  # the same lines on Telegram, when the bot is linked (quietly nothing otherwise)
        extra = ("\n\nThe e-mail copy could not be sent: " + mail_error) if mail_error else (
            "" if sent else "\n\n(No e-mail copy: no sender or no address.)")
        told = bool(telegram_bot.notify(store, f"🩺 {subject}\n\n" + as_text(body) + extra))
    if sent or told:                             # only once Wan has been told, by either: if neither went, say it again
        state["open"] = now_open
    if sent:
        state["emailed_fingerprint"] = fingerprint(problems)
        if kind == "summary":
            state["summary_at"] = now.isoformat()
    if not kind:
        state["open"] = now_open
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
