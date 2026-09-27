-- Semasa · ws.regulab Studio's day-to-day workflow, brought over (Wan, 27 Sep 2026: "make sure all ws.regulab studio
-- features ... is brought to the new system"). Run ONCE in the SQL editor, after 001–020. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): columns are ADDED to semasa_posts, one Semasa trigger function is added, and one
-- settings row is seeded. No data is changed, no policy is touched, no other app's object is read or written.
--
-- 1. versions      the words a post had before each rewrite (Studio's versions): a rewrite never loses what it replaced
-- 2. decisions     who approved, rejected, restored, revised or replaced it, when, and why (Studio's decisions)
-- 3. rejected_at   stamped by the database the moment a post is rejected; a rejected post is removed 72 hours later
--                  by the worker, unless it carries a delivery record (Studio's purgeRejected, same three guards)
-- 4. revise_*      "Revise with a note": the page asks, the worker rewrites the same subject with the note, keeps the
--                  old words in versions, and never touches an approved post
-- 5. pillar      the writer's label for the post, from the domain's pillar list in settings "writer" (Studio's pillars)
-- 6. settings "writer"  voice, never-list, hashtag lists, pillars and the fatwa gazette line for each stream,
--                  seeded from Studio's own Settings and edited in Semasa's Settings tab; read by every writer in the worker

alter table public.semasa_posts add column if not exists versions     jsonb       not null default '[]'::jsonb;
alter table public.semasa_posts add column if not exists decisions    jsonb       not null default '[]'::jsonb;
alter table public.semasa_posts add column if not exists rejected_at  timestamptz;
alter table public.semasa_posts add column if not exists revise_note  text;
alter table public.semasa_posts add column if not exists revise_state text;
alter table public.semasa_posts add column if not exists revise_error text;
alter table public.semasa_posts add column if not exists pillar       text;
alter table public.semasa_posts drop constraint if exists semasa_posts_revise_state_check;
alter table public.semasa_posts add constraint semasa_posts_revise_state_check
  check (revise_state is null or revise_state in ('new', 'working', 'error'));

-- 3: the database stamps it, so a page, the worker and a hand edit in the SQL editor all count the 72 hours the same
create or replace function public.semasa_posts_rejected_at() returns trigger
language plpgsql set search_path = public as $$
begin
  if new.status = 'rejected' then
    if tg_op = 'INSERT' or old.status is distinct from 'rejected' or new.rejected_at is null then
      new.rejected_at := coalesce(case when tg_op = 'UPDATE' and old.status = 'rejected' then old.rejected_at end, now());
    end if;
  else
    new.rejected_at := null;
  end if;
  return new;
end $$;
drop trigger if exists semasa_posts_rejected_at on public.semasa_posts;
create trigger semasa_posts_rejected_at before insert or update on public.semasa_posts
  for each row execute function public.semasa_posts_rejected_at();

-- posts rejected before this file ran start their 72 hours from the last change, not from nothing
update public.semasa_posts set rejected_at = updated_at where status = 'rejected' and rejected_at is null;

-- 4: a revise request wakes the worker the way a new idea does (005: semasa_notify_idea_new)
drop trigger if exists semasa_posts_notify_revise on public.semasa_posts;
create trigger semasa_posts_notify_revise
  after update of revise_state on public.semasa_posts
  for each row when (new.revise_state = 'new')
  execute function public.semasa_notify_idea_new();

-- 6
-- Studio's own writer settings (settings/brand, read 27 Sep 2026), so the worker writes in Wan's voice from the first run.
-- One change on the way in: Studio's never-list told the writer to write "[SAHKAN: ...]" for a fact it could not
-- source. Semasa has no [SAHKAN] (Wan, 26 Sep 2026) and nothing here looks for one, so those two lines now say what
-- Semasa's writers are told everywhere else: leave the fact out and write around it. A row already there is kept.
insert into public.semasa_settings (key, value) values ('writer', $writer${
 "regulab": {
  "voice": "Like a consultant who has handled 200 files, not a government brochure. Blunt: if the process is a hassle, say so. One idea per post. Use 'anda'. Real specifics beat adjectives. Warm, casual, human.",
  "never": [
   "Never use the name 'KKM Halal Consultant'. KKM only as the ministry.",
   "Never promise approval or imply an official relationship with KKM, NPRA or JAKIM.",
   "Never state a fee, timeline, circular number or notification number you cannot source: leave it out and write around it.",
   "Never name a client.",
   "No halal claim for any product without a certificate number; talking about the process is fine.",
   "No 'Tahukah anda', no 'Dalam dunia yang serba pantas', no 'Adalah dimaklumkan', no emoji bullets, no rule-of-three every paragraph."
  ],
  "hashtags_core": [
   "#SijilHalal",
   "#JAKIM",
   "#KKM",
   "#NPRA",
   "#SMEMalaysia"
  ],
  "hashtags_rotate": [
   "#UsahawanMalaysia",
   "#HalalMalaysia",
   "#KosmetikMalaysia",
   "#ProdukTempatan",
   "#RegulatoryAffairs",
   "#MyHalal",
   "#PelabelanMakanan",
   "#FSQD"
  ],
  "fatwa_warning": "Keputusan Muzakarah MKI bukan undang-undang secara automatik. Ia mengikat di sesebuah negeri hanya selepas diwartakan oleh Jawatankuasa Fatwa Negeri.",
  "pillars": {
   "farmaseutikal": [
    "kajian_kes",
    "mitos",
    "urutan",
    "kos_tempoh",
    "dokumen",
    "soal_jawab"
   ],
   "fatwa": [
    "kajian_kes",
    "soal_jawab",
    "mitos"
   ],
   "halal_my": [
    "kajian_kes",
    "urutan",
    "silap",
    "soal_jawab",
    "kos_tempoh",
    "mitos",
    "dokumen"
   ],
   "kajian_kes": [
    "kajian_kes"
   ],
   "kosmetik": [
    "kajian_kes",
    "dokumen",
    "silap",
    "soal_jawab",
    "kos_tempoh",
    "mitos"
   ],
   "makanan": [
    "kajian_kes",
    "dokumen",
    "mitos",
    "silap",
    "soal_jawab"
   ],
   "sains_kosmetik": [
    "kajian_kes",
    "kajian_sains"
   ]
  }
 },
 "linkedin": {
  "voice": "A named professional writing in his own voice: hook on line one, one idea per post, a concrete example (ingredient name, Annex entry, real figure), short paragraphs of one or two sentences, casual-professional, human. Body 120 to 220 words. Citations below the body, never inside it. End on a statement that lands, never a question. 3 to 5 hashtags. No em dashes.",
  "never": [
   "Never write or review claims for Wan's own brands.",
   "Never name a client, formula code or file.",
   "Never invent a URL, date, entry number or figure: leave out a value you cannot source and write around it.",
   "Never end with a question.",
   "Never add a 'consult a professional' disclaimer."
  ]
 }
}$writer$::jsonb)
  on conflict (key) do nothing;

-- Check (should print 1 | 1 | 1):
--   select (select count(*) from information_schema.columns where table_name = 'semasa_posts'
--             and column_name in ('versions', 'decisions', 'rejected_at', 'revise_note', 'revise_state', 'revise_error',
--                                 'pillar')) / 7,
--          (select count(*) from pg_trigger where tgname in ('semasa_posts_rejected_at', 'semasa_posts_notify_revise')) / 2,
--          (select count(*) from public.semasa_settings where key = 'writer');
