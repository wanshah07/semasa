# Studio link — Routine instructions

This file is the whole instruction for the **Studio link** Routine. The Routine's own prompt only points here; edit this
file and the Routine follows. Never paste this body into the trigger.

**Why it exists** (Wan, 27 Sep 2026: *"link ws.regulab studio with the system, so once the draft posted, deleted
automatically in the system, until I instruct to retire the studio"*). Studio's drafts were copied into Semasa once.
Studio keeps posting them. When a Studio post goes out, its Semasa copy must leave the drafts, or approving it in Semasa
too would post the same story twice. Semasa files the copy in the Arkib as `posted` (it keeps the idea's
never-write-twice link); `backend/semasa/studio_link.py` does that when this Routine starts the `studio-link` workflow.

**It runs until Wan says to retire Studio.** Then the Routine is deleted. If the line below says RETIRED, stop at once,
do nothing else and report "Studio retired: nothing to do".

Status: RETIRED (Fri 2 Oct 2026, cutover). Studio's release Routine, nightly drafter and this link Routine were disabled
at 19:47 MYT and Studio's queue was imported into Semasa the same night. This Routine (trig_01Nu26P8gBCt23h7B6KbvfYy) is
disabled and is deleted with Studio.

## What this Routine may and may not do

- It READS Studio's store. It never writes to Studio's store, never posts, never touches Buffer, LinkedIn or Composio,
  and never approves anything anywhere.
- It starts ONE workflow in `wanshah07/semasa`: `studio-link.yml`. Nothing else in that repo.
- A picture's bytes never cross the conversation. Nothing here needs a picture.

## Steps

1. **Repo.** `add_repo(owner="wanshah07", repo="semasa", access="push")` — the workflow start needs it. If it is refused,
   stop and report the refusal word for word; do not look for another route.

2. **Read Studio's posted drafts into an EMPTY directory.** An `out_dir` that already holds files from an earlier read
   gives a false answer (a document deleted since still sits there), so:
   `rm -rf /tmp/studio-link && mkdir -p /tmp/studio-link`, then
   `ArtifactData` `query` on `https://claude.ai/code/artifact/531c7408-8042-4ebe-b729-2e8cfad7258a`, collection
   `drafts`, `query: {"where": [["status", "==", "posted"]], "limit": 1000}`, `out_dir: "/tmp/studio-link"`.
   Count the files the tool REPORTS; that count is the measurement, not a glob of the directory.

3. **Build the message on disk** (the captions stay on disk; only delivery ids and times go out):

   ```bash
   python3 - <<'EOF'
   import glob, json, re
   from datetime import datetime, timedelta, timezone
   cut = datetime.now(timezone.utc) - timedelta(days=10)      # older posts were filed on earlier runs
   out = {}
   for f in glob.glob("/tmp/studio-link/drafts/*.json"):
       d = json.load(open(f))
       sid = f.rsplit("/", 1)[1][:-5]
       recs = {}
       for ch, r in (d.get("published") or {}).items():
           if ch not in ("instagram", "facebook", "threads", "linkedin") or not isinstance(r, dict):
               continue
           m = re.match(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})", str(r.get("at") or ""))
           when = (datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:00+08:00") if m else None)
           if when is None or when >= cut:
               recs[ch] = {k: str(r[k]) for k in ("id", "at", "url") if r.get(k)}
       if recs:
           out[sid] = recs
   s = json.dumps(out, separators=(",", ":"))
   assert len(s) < 60000, f"message too long ({len(s)}); shorten the 10-day window"
   open("/tmp/studio-link/posted.json", "w").write(s)
   print(len(out), "posted drafts,", len(s), "characters")
   EOF
   ```

   If it prints `0 posted drafts`, stop and report "Studio posted nothing in the last 10 days".

4. **Start the workflow** with GitHub's `actions_run_trigger`: method `run_workflow`, owner `wanshah07`, repo
   `semasa`, workflow_id `studio-link.yml`, ref `main`, inputs `{"posted": <the exact contents of posted.json>}`.
   Paste the file's contents exactly as printed by `cat /tmp/studio-link/posted.json`; do not edit them.

5. **Confirm it ran.** Wait about a minute, then list the workflow's latest run and read its conclusion. Report, in one
   short reply: how many Studio drafts were in the message, the run's link and its conclusion. The run's summary says how
   many copies were filed, how many were already history and how many Semasa never had (drafts made in Studio after the
   import). A failed run is reported with its log's last error line; it is never retried in the same Routine run (the
   next run carries the same drafts again, and filing is safe to repeat).
