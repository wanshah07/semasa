import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, CalendarClock, Loader2, Play } from "lucide-react";
import { DAILY, LANES, SETTING, STATE, dailyConfig, dayStatusWords, episodesOf, laneRows, logLines, makeNowAnswer, moveLane, mytDay, statusWords,
  toggleLane, todayOf, withConfig, withMakeNow } from "../lib/comicDaily";
import { comicLibrary } from "../lib/comic";
import { useLang } from "../lib/i18n";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import MotionStoryboardReview from "./MotionStoryboardReview";
import Button from "./ui/Button";
import { Input, Label, Segmented, Select } from "./ui/Field";

/* The daily comic series (Wan, 17 Nov 2026: "can start create comic series storyboard and after approve create motion - this series
   will comeout everyday which contain about isu semasa>halal>regulatory>fatwa"). Each morning the worker takes the best item from the
   feed (the lanes below, in this order), writes the four-panel storyboard and STOPS here: nothing is drawn until it is approved, on
   this page or in Telegram. The approval is the Motion storyboard gate (supabase/071), so the buttons are the same ones. After it the
   comic is drawn once, made into a film, and a DRAFT post is made; the post's own Approve stays Wan's. Settings are the row
   `comic_series` (supabase/086); the worker's record of days is `comic_series_log`. */

const TONE = { ok: "text-ok", warn: "text-warn", danger: "text-danger", muted: "text-muted" };

export default function ComicDailyPanel({ settings, saveSetting, onToast, go }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const value = settings?.[SETTING];
  const cfg = useMemo(() => dailyConfig(value), [value]);
  const lib = useMemo(() => comicLibrary(settings?.comic), [settings?.comic]);
  const [rows, setRows] = useState([]);
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState("");
  const [loadError, setLoadError] = useState("");
  const row = value !== undefined;

  const load = useCallback(async () => {
    const [m, s] = await Promise.all([
      supabase.from(TABLES.motions).select("id,status,stage,error,options,title,created_at,queued_post_id,storyboard,storyboard_approved_at,video_url,poster_url,duration_s")
        .eq("options->>template", "comic").order("created_at", { ascending: false }).limit(40),
      supabase.from(TABLES.settings).select("value").eq("key", STATE).maybeSingle(),
    ]);
    if (m.error) setLoadError(errText(m.error)); else { setLoadError(""); setRows(m.data || []); }
    if (!s.error) setState(s.data?.value || null);
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  const episodes = useMemo(() => episodesOf(rows), [rows]);
  const today = todayOf(episodes);
  const log = useMemo(() => logLines(state), [state]);
  const skippedToday = !today && log.find((x) => x.day === mytDay() && x.status === "skipped");
  const answer = makeNowAnswer(cfg, state);

  async function save(patch, msg) {
    setBusy("save");
    try {
      await saveSetting(SETTING, withConfig(value, patch));
      if (msg) onToast(msg, "ok");
    } catch (e) {
      onToast(/not found/.test(e.message || "") ? t("Belum disediakan: jalankan supabase/086_comic_daily.sql sekali dalam Supabase, kemudian cuba lagi.",
        "Not set up yet: run supabase/086_comic_daily.sql once in Supabase, then try again.") : (e.message || String(e)), "danger");
    } finally {
      setBusy("");
    }
  }
  async function makeNow() {
    setBusy("now");
    try {
      await saveSetting(SETTING, withMakeNow(value));
      onToast(t("Diminta. Worker menulis storyboard dalam beberapa minit dan menghantarnya ke sini dan Telegram.", "Asked. The worker writes the storyboard within a few minutes and sends it here and on Telegram."), "ok");
      setTimeout(load, 15_000);
      setTimeout(load, 60_000);
    } catch (e) {
      onToast(/not found/.test(e.message || "") ? t("Belum disediakan: jalankan supabase/086_comic_daily.sql sekali dalam Supabase.", "Not set up yet: run supabase/086_comic_daily.sql once in Supabase.") : (e.message || String(e)), "danger");
    } finally {
      setBusy("");
    }
  }

  const lanes = laneRows(cfg);
  const say = (x) => (L ? x.en : x.bm);
  return (
    <details className="mt-6 rounded-card border border-line/80 bg-surface p-4" open data-comic-daily>
      <summary className="cursor-pointer text-sm font-semibold">{t("Siri harian: isu semasa, halal, regulatori, fatwa", "The daily series: current issue, halal, regulatory, fatwa")}
        <span className={`ml-2 font-normal ${cfg.enabled && !cfg.paused ? "text-ok" : "text-muted"}`} data-daily-state>
          {!cfg.enabled ? t("mati", "off") : cfg.paused ? t("dijeda", "paused") : t("hidup", "on")}</span></summary>
      <p className="mt-2 max-w-3xl text-[12px] text-muted">{t("Setiap pagi Semasa memilih satu item daripada suapan dan menulis storyboard empat panel, kemudian berhenti dan menunggu anda. Tiada gambar dibayar sebelum anda luluskan. Selepas itu komik dilukis sekali, dijadikan filem, dan draf post dibuat; Lulus post itu tetap milik anda.",
        "Each morning Semasa picks one item from the feed and writes a four-panel storyboard, then stops and waits for you. No picture is paid for before you approve. After that the comic is drawn once, made into a film, and a draft post is made; the post's own Approve stays yours.")}</p>
      {!row && <p className="mt-2 rounded-tile bg-warn/10 p-2 text-[12px] text-warn" data-daily-needs-sql>{t("Untuk menyimpan tetapan siri harian, jalankan supabase/086_comic_daily.sql sekali dalam Supabase.", "To save the daily series' settings, run supabase/086_comic_daily.sql once in Supabase.")}</p>}
      {loadError && <p className="mt-2 text-[12px] text-warn">{loadError}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={cfg.enabled} disabled={!row || busy === "save"} data-daily-switch
          onChange={(e) => save({ enabled: e.target.checked }, e.target.checked ? t("Siri harian dihidupkan.", "The daily series is on.") : t("Siri harian dimatikan.", "The daily series is off."))} />
          {t("Hidupkan siri harian", "Switch the daily series on")}</label>
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={cfg.paused} disabled={!row || busy === "save"} data-daily-pause
          onChange={(e) => save({ paused: e.target.checked }, e.target.checked ? t("Dijeda: tiada episod dibuat.", "Paused: no episode is made.") : t("Disambung semula.", "Resumed."))} />
          {t("Jeda", "Pause")}</label>
        <Button type="button" size="sm" variant="soft" disabled={!row || busy === "now"} onClick={makeNow} data-daily-now>
          {busy === "now" ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} {t("Buat episod hari ini sekarang", "Make today's episode now")}</Button>
      </div>
      {answer && <p className={`mt-1.5 text-[12px] ${answer.status === "planned" ? "text-ok" : "text-muted"} [overflow-wrap:anywhere]`} data-daily-answer>
        {answer.status === "waiting" ? t("Menunggu worker menjawab permintaan anda...", "Waiting for the worker to answer your request...")
          : answer.status === "planned" ? t("Worker membuat episod hari ini.", "The worker made today's episode.")
            : answer.status === "exists" ? t("Episod hari ini sudah ada; satu sehari sahaja.", "Today's episode already exists; one a day at most.")
              : `${t("Tiada episod dibuat", "No episode was made")}: ${answer.reason || answer.status}`}</p>}
      <p className="mt-1 text-[11px] text-muted">{t("Butang ini menulis storyboard sahaja dan tidak peduli suis atau jeda; satu episod sehari tetap berlaku.", "This button only writes a storyboard and ignores the switch and the pause; one episode a day still holds.")}</p>

      {/* today's episode and the storyboard waiting for approval */}
      <div className="mt-4 rounded-tile border border-line p-3" data-daily-today>
        <p className="flex items-center gap-1.5 text-[13px] font-semibold"><CalendarClock size={14} /> {t("Hari ini", "Today")}</p>
        {today ? (
          <>
            <p className="mt-1 text-[13px] [overflow-wrap:anywhere]"><b>{t("Episod", "Episode")} {today.episode}</b>{today.title ? ` · ${today.title}` : ""}
              <span className="ml-2 rounded-pill bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">{say((LANES.find((l) => l.id === today.lane) || { name: { bm: today.lane, en: today.lane } }).name)}</span></p>
            <p className={`mt-0.5 text-[12px] ${TONE[statusWords(today)[2]] || "text-muted"}`} data-daily-status>{statusWords(today)[L]}</p>
            {today.error && <p className="mt-1 text-[12px] text-danger [overflow-wrap:anywhere]" data-daily-error>{today.error}</p>}
            {today.status === "review" && <MotionStoryboardReview film={today.row} onDone={load} onToast={onToast} />}
          </>
        ) : skippedToday ? (
          <p className="mt-1 text-[12px] text-warn [overflow-wrap:anywhere]" data-daily-skipped>{t("Tiada episod hari ini: tiada item yang sesuai.", "No episode today: no fitting item.")} {skippedToday.reason}</p>
        ) : (
          <p className="mt-1 text-[12px] text-muted">{cfg.enabled && !cfg.paused
            ? t("Belum ada episod hari ini. Worker membuatnya selepas {at} (waktu Malaysia), kira-kira jam 07:00.", "No episode yet today. The worker makes it after {at} (Malaysia time), about 07:00.", { at: cfg.at })
            : t("Siri ini mati atau dijeda; tiada episod dibuat sendiri.", "The series is off or paused; no episode is made by itself.")}</p>
        )}
      </div>

      {/* the lanes, in the order the worker tries them */}
      <div className="mt-4" data-daily-lanes>
        <Label hint={t("pilih item pertama yang sesuai mengikut susunan ini; lorong tanpa item hari itu dilangkau", "the first fitting item in this order is taken; a lane with no item that day is skipped")}>{t("Lorong dan susunannya", "Lanes and their order")}</Label>
        <ol className="mt-1 space-y-1.5">
          {lanes.map((l) => {
            const i = cfg.lanes.indexOf(l.id);
            return (
              <li key={l.id} className={`rounded-tile border p-2 text-[12px] ${l.on ? "border-line" : "border-line/60 opacity-70"}`} data-daily-lane={l.id}>
                <div className="flex flex-wrap items-center gap-2">
                  <input type="checkbox" checked={l.on} disabled={!row || busy === "save"} aria-label={`${say(l.name)}: ${t("hidupkan", "switch on")}`}
                    onChange={() => save({ lanes: toggleLane(cfg.lanes, l.id) })} />
                  <b className="text-[13px]">{l.on ? `${i + 1}. ` : ""}{say(l.name)}</b>
                  {l.on && (
                    <span className="ml-auto flex gap-1">
                      <button type="button" className="rounded p-1 text-muted hover:text-accent disabled:opacity-30" disabled={i === 0 || !row} aria-label={t("Naik", "Move up")} onClick={() => save({ lanes: moveLane(cfg.lanes, l.id, -1) })}><ArrowUp size={13} /></button>
                      <button type="button" className="rounded p-1 text-muted hover:text-accent disabled:opacity-30" disabled={i === cfg.lanes.length - 1 || !row} aria-label={t("Turun", "Move down")} onClick={() => save({ lanes: moveLane(cfg.lanes, l.id, 1) })}><ArrowDown size={13} /></button>
                    </span>
                  )}
                </div>
                <p className="mt-1 text-muted [overflow-wrap:anywhere]">{say(l.reads)}</p>
              </li>
            );
          })}
        </ol>
        {cfg.lanes.length === 0 && <p className="mt-1 text-[12px] text-warn">{t("Tiada lorong dihidupkan: tiada episod boleh dibuat.", "No lane is on: no episode can be made.")}</p>}
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <label className="block"><Label hint={t("waktu Malaysia; storyboard siap kira-kira sejam kemudian", "Malaysia time; the storyboard is ready about an hour later")}>{t("Mula selepas", "Start after")}</Label>
          <Input type="time" value={cfg.at} disabled={!row} className="max-w-[9rem]" data-daily-at onChange={(e) => e.target.value && save({ at: e.target.value })} /></label>
        <label className="block"><Label hint={t("dua watak tetap pada setiap episod", "the same two people in every episode")}>{t("Siri", "Series")}</Label>
          <Select value={cfg.series} disabled={!row} className="w-full" aria-label={t("Siri", "Series")} options={lib.series.map((s) => [s.id, s.name])} onChange={(v) => save({ series: v })} /></label>
        <div><Label>{t("Perkataan dalam gelembung", "Words in the bubbles")}</Label>
          <Segmented value={cfg.wordsMode} onChange={(v) => save({ words_mode: v })} options={[["art", t("Semasa cetak (disyorkan)", "Semasa prints (recommended)")], ["auto", t("Pelukis tulis, Semasa semak", "The maker writes, Semasa checks")]]} />
          <span className="mt-1 block text-[11px] text-muted">{cfg.wordsMode === "art"
            ? t("Satu lukisan sahaja, perkataan tepat, dan gelembung muncul satu demi satu dalam filem.", "One drawing, exact words, and the bubbles appear one by one in the film.")
            : t("Sehingga dua lukisan dan satu bacaan; filem menunjukkan panel seperti dilukis.", "Up to two drawings and a read-back; the film shows the panels as drawn.")}</span></div>
      </div>

      {/* past episodes */}
      <div className="mt-5" data-daily-episodes>
        <Label>{t("Episod lepas", "Past episodes")}</Label>
        {episodes.length === 0 ? <p className="mt-1 text-[12px] text-muted">{t("Belum ada episod.", "No episodes yet.")}</p> : (
          <ul className="mt-1 divide-y divide-line/60 text-[12px]">
            {episodes.slice(0, 12).map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5" data-daily-episode={e.id}>
                <span className="w-16 shrink-0 font-semibold">{t("Episod", "Ep.")} {e.episode}</span>
                <span className="text-muted">{e.day}</span>
                <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{e.title || "-"}</span>
                <span className={TONE[statusWords(e)[2]] || "text-muted"}>{statusWords(e)[L]}</span>
                {e.videoUrl && <a href={e.videoUrl} target="_blank" rel="noreferrer" className="text-accent underline">{t("Filem", "Film")}</a>}
                {e.postId && go && <button type="button" className="text-accent underline" onClick={() => go("post")}>{t("Draf post", "Draft post")}</button>}
                {e.error && e.status !== "review" && <span className="w-full text-danger [overflow-wrap:anywhere]">{e.error}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* the worker's record of days, so a day with no episode says why */}
      <div className="mt-4" data-daily-log>
        <Label>{t("Hari yang dilihat", "Days looked at")}</Label>
        {log.length === 0 ? <p className="mt-1 text-[12px] text-muted">{t("Belum ada.", "None yet.")}</p> : (
          <ul className="mt-1 space-y-1 text-[12px]">
            {log.slice(0, 10).map((x, i) => (
              <li key={`${x.day}-${x.status}-${i}`} className="[overflow-wrap:anywhere]">
                <span className="text-muted">{x.day}</span> · <b className={x.status === "skipped" ? "text-warn" : "text-ok"}>{dayStatusWords(x.status)[L]}</b>
                {x.status === "planned" ? ` · ${t("episod", "episode")} ${x.episode || ""} · ${x.lane}` : x.reason ? ` · ${x.reason}` : ""}</li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[11px] text-muted">{t("Sumber lorong: {n} lorong, susunan asal {d}.", "Lane sources: {n} lanes, default order {d}.", { n: LANES.length, d: DAILY.lanes.join(" > ") })}</p>
      </div>
    </details>
  );
}
