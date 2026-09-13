-- ===========================================================================
-- Zagreb Marathon photo search — Supabase schema
--
-- Run this once in the Supabase SQL editor (or `supabase db push`).
-- Safe to re-run: everything is idempotent.
--
-- Two ideas carry the whole design:
--
--  1. Detections are candidates, not answers. The OCR pipeline stores *every*
--     reading it produced for a bib, with its confidence and rank. Matching a
--     runner to photos then happens at query time as exact ∪ edit-distance-1,
--     ranked by confidence × similarity. That is what turns 78.8% exact into
--     ~98.5% fuzzy@1 (see the repo README) without touching the model.
--
--  2. Birthdates never leave Postgres. `runners` is unreadable to the anon
--     key; the only way in is find_runner(), a SECURITY DEFINER function that
--     still holds the dob check but currently runs with it switched off — the
--     app passes a null p_dob, so a bib alone opens a gallery. Pass a date
--     again to turn verification back on. That is what lets the site be a
--     static export with no server of its own.
-- ===========================================================================

create extension if not exists pg_trgm;        -- trigram similarity + GIN index
create extension if not exists fuzzystrmatch;  -- levenshtein()
create extension if not exists "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Events and races
-- ---------------------------------------------------------------------------

create table if not exists public.events (
  id          uuid primary key default uuid_generate_v4(),
  slug        text not null unique,
  name        text not null,
  edition     int,
  race_date   date,
  city        text default 'Zagreb',
  -- Landing-page numbers that are editorial rather than derived.
  first_year  int,
  -- Gate for RLS: nothing is publicly readable until this flips.
  published   boolean not null default false,
  created_at  timestamptz not null default now()
);

create table if not exists public.races (
  id          uuid primary key default uuid_generate_v4(),
  event_id    uuid not null references public.events(id) on delete cascade,
  code        text not null,               -- 'marathon' | 'half' | '10k'
  name        text not null,               -- 'Marathon'
  distance_km numeric(7,4) not null,       -- 42.1950
  unique (event_id, code)
);

-- ---------------------------------------------------------------------------
-- Runners — one row per bib per event. Contains PII; never exposed directly.
-- ---------------------------------------------------------------------------

create table if not exists public.runners (
  id             uuid primary key default uuid_generate_v4(),
  event_id       uuid not null references public.events(id) on delete cascade,
  race_id        uuid references public.races(id) on delete set null,
  bib            text not null,
  dob            date,                     -- the shared secret for the search
  full_name      text not null,
  gender         text,                     -- 'F' | 'M' | null
  category       text,                     -- 'W35', 'M45', …
  club           text,
  nationality    text,
  finish_time    interval,                 -- gun/official time
  chip_time      interval,
  place_overall  int,
  place_gender   int,
  place_category int,
  status         text default 'finished',  -- finished | dnf | dns | dsq
  created_at     timestamptz not null default now(),
  unique (event_id, bib)
);

create index if not exists runners_event_bib_idx on public.runners (event_id, bib);

-- Pace, derived — never stored, so it can never disagree with finish_time.
create or replace function public.runner_pace(p_time interval, p_km numeric)
returns text language sql immutable as $$
  select case
    when p_time is null or p_km is null or p_km = 0 then null
    else to_char(
      make_interval(secs => round(extract(epoch from p_time) / p_km)),
      'FMMI:SS')
  end;
$$;

-- ---------------------------------------------------------------------------
-- Photos and detections
-- ---------------------------------------------------------------------------

create table if not exists public.photos (
  id            uuid primary key default uuid_generate_v4(),
  event_id      uuid not null references public.events(id) on delete cascade,
  file_name     text not null,             -- as it came off the card / CSV
  -- Storage keys. `preview_path` is the public, watermarked, web-sized image;
  -- `original_path` sits in a private bucket and is only ever handed out as a
  -- signed URL after a purchase.
  preview_path  text,
  original_path text,
  width         int,
  height        int,
  captured_at   timestamptz,
  photographer  text,
  course_point  text,                      -- 'Start', '10K', 'Finish', …
  course_km     numeric(6,3),
  created_at    timestamptz not null default now(),
  unique (event_id, file_name)
);

create index if not exists photos_event_idx on public.photos (event_id);

create table if not exists public.detections (
  id          uuid primary key default uuid_generate_v4(),
  photo_id    uuid not null references public.photos(id) on delete cascade,
  bib_text    text not null,               -- normalised digits, 2–6 chars
  confidence  numeric(5,4),                -- recognizer confidence, 0–1
  rank        int not null default 0,      -- 0 = top candidate for that crop
  bbox        jsonb,                       -- {x0,y0,x1,y1} in source pixels
  crop_height int,                         -- drives the accuracy bucket
  source      text not null default 'ocr'  -- 'ocr' | 'manual' | 'review'
);

-- The index that makes fuzzy search cheap. Trigrams on the candidate text.
create index if not exists detections_bib_trgm_idx
  on public.detections using gin (bib_text gin_trgm_ops);
create index if not exists detections_bib_idx on public.detections (bib_text);
create index if not exists detections_photo_idx on public.detections (photo_id);

-- ---------------------------------------------------------------------------
-- Purchases (prototype: rows are written by the app, no payment provider yet)
-- ---------------------------------------------------------------------------

create table if not exists public.orders (
  id          uuid primary key default uuid_generate_v4(),
  event_id    uuid not null references public.events(id) on delete cascade,
  bib         text not null,
  kind        text not null,               -- 'single' | 'bundle'
  photo_id    uuid references public.photos(id) on delete set null,
  amount_eur  numeric(8,2),
  created_at  timestamptz not null default now()
);

-- ===========================================================================
-- Row level security
--
-- The anon key gets: nothing on runners, nothing on orders, read-only on
-- photos and detections for published events. Everything else goes through
-- the two functions below.
-- ===========================================================================

alter table public.events     enable row level security;
alter table public.races      enable row level security;
alter table public.runners    enable row level security;
alter table public.photos     enable row level security;
alter table public.detections enable row level security;
alter table public.orders     enable row level security;

drop policy if exists "events readable when published" on public.events;
create policy "events readable when published" on public.events
  for select using (published);

drop policy if exists "races readable when published" on public.races;
create policy "races readable when published" on public.races
  for select using (exists (
    select 1 from public.events e where e.id = races.event_id and e.published));

drop policy if exists "photos readable when published" on public.photos;
create policy "photos readable when published" on public.photos
  for select using (exists (
    select 1 from public.events e where e.id = photos.event_id and e.published));

drop policy if exists "detections readable when published" on public.detections;
create policy "detections readable when published" on public.detections
  for select using (exists (
    select 1 from public.photos p join public.events e on e.id = p.event_id
    where p.id = detections.photo_id and e.published));

-- No policies on public.runners or public.orders at all: with RLS on and no
-- permissive policy, anon and authenticated see zero rows. Deliberate.

-- ===========================================================================
-- find_runner — the only door into runner data
--
-- Returns null unless the bib exists in the event. Birthdate verification is
-- off for now: p_dob defaults to null and the check is skipped when it is,
-- so passing a date again is all it takes to bring it back.
-- On success returns the runner plus every photo whose detections point at
-- that bib, ranked by confidence × trigram similarity.
--
-- `match_kind` is carried through to the UI: 'exact' means a detection read
-- the bib verbatim, 'fuzzy' means it was one edit away. A false positive puts
-- a stranger in your gallery, so the two are never silently mixed.
-- ===========================================================================

create or replace function public.find_runner(
  p_event_slug text,
  p_bib        text,
  p_dob        date default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_event  public.events;
  v_runner public.runners;
  v_race   public.races;
  v_bib    text := regexp_replace(coalesce(p_bib, ''), '\D', '', 'g');
  v_photos jsonb;
begin
  if v_bib = '' then
    return jsonb_build_object('ok', false, 'reason', 'missing_input');
  end if;

  select * into v_event from public.events
   where slug = p_event_slug and published;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'no_event');
  end if;

  select * into v_runner from public.runners
   where event_id = v_event.id and bib = v_bib;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'no_bib');
  end if;

  -- Only enforced when a date is supplied. Same generic answer whether the bib
  -- is unknown or the date is wrong would be more private, but the design shows
  -- two distinct messages, so we keep them. The date itself is never echoed
  -- back either way.
  if p_dob is not null and v_runner.dob is distinct from p_dob then
    return jsonb_build_object('ok', false, 'reason', 'dob_mismatch');
  end if;

  select * into v_race from public.races where id = v_runner.race_id;

  -- Ordered by distance along the course, then by time. Both have to be sorted
  -- as numbers/timestamps rather than as JSON text, or 5K lands after 42.195.
  select coalesce(jsonb_agg(x order by km nulls last, shot nulls last), '[]'::jsonb)
    into v_photos
  from (
    select p.course_km as km, p.captured_at as shot, jsonb_build_object(
             'id',            p.id,
             'file_name',     p.file_name,
             'preview_path',  p.preview_path,
             'original_path', p.original_path,
             'width',         p.width,
             'height',        p.height,
             'captured_at',   p.captured_at,
             'photographer',  p.photographer,
             'course_point',  p.course_point,
             'course_km',     p.course_km,
             'match_kind',    d.match_kind,
             -- similarity() is float4, and round(double, int) does not exist.
             'match_score',   round(d.score::numeric, 4),
             'read_as',       d.bib_text
           ) as x
    from public.photos p
    join lateral (
      select
        det.bib_text,
        case when det.bib_text = v_bib then 'exact' else 'fuzzy' end as match_kind,
        max(coalesce(det.confidence, 0.5)
            * case when det.bib_text = v_bib then 1.0
                   else greatest(similarity(det.bib_text, v_bib), 0.2) end
        ) as score
      from public.detections det
      where det.photo_id = p.id
        and (
          det.bib_text = v_bib
          -- one edit away, and only for bibs of a plausible length. Truncation
          -- ("1514" read as "514") is the dominant failure mode, so prefix and
          -- suffix loss both have to be reachable.
          or (length(det.bib_text) between greatest(2, length(v_bib) - 1)
                                       and length(v_bib) + 1
              and levenshtein(det.bib_text, v_bib) <= 1)
        )
      group by det.bib_text
      order by 3 desc
      limit 1
    ) d on true
    where p.event_id = v_event.id
  ) s;

  return jsonb_build_object(
    'ok', true,
    'runner', jsonb_build_object(
      'bib',            v_runner.bib,
      'name',           v_runner.full_name,
      'category',       v_runner.category,
      'club',           v_runner.club,
      'nationality',    v_runner.nationality,
      'race',           coalesce(v_race.name, 'Marathon'),
      'race_code',      coalesce(v_race.code, 'marathon'),
      'distance_km',    coalesce(v_race.distance_km, 42.195),
      'status',         v_runner.status,
      'time',           case when v_runner.finish_time is null then null
                             else to_char(v_runner.finish_time, 'FMHH24:MI:SS') end,
      'pace',           public.runner_pace(v_runner.finish_time,
                                           coalesce(v_race.distance_km, 42.195)),
      'place_overall',  v_runner.place_overall,
      'place_category', v_runner.place_category
    ),
    'photos', v_photos
  );
end;
$$;

revoke all on function public.find_runner(text, text, date) from public;
grant execute on function public.find_runner(text, text, date) to anon, authenticated;

-- ===========================================================================
-- event_stats — the landing page counters. Aggregates only, no PII.
-- ===========================================================================

create or replace function public.event_stats(p_event_slug text)
returns jsonb
language sql
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'ok', e.id is not null,
    'name', e.name,
    'edition', e.edition,
    'race_date', e.race_date,
    'city', e.city,
    'first_year', e.first_year,
    'finishers', (select count(*) from public.runners r
                   where r.event_id = e.id and r.status = 'finished'),
    'photos', (select count(*) from public.photos p where p.event_id = e.id),
    'tagged_bibs', (select count(distinct d.bib_text)
                      from public.detections d
                      join public.photos p on p.id = d.photo_id
                     where p.event_id = e.id),
    'distance_km', (select max(distance_km) from public.races ra
                     where ra.event_id = e.id),
    'course_record', (select to_char(min(r.finish_time), 'FMHH24:MI:SS')
                        from public.runners r
                        join public.races ra on ra.id = r.race_id
                       where r.event_id = e.id and ra.code = 'marathon'
                         and r.status = 'finished')
  )
  from public.events e
  where e.slug = p_event_slug and e.published;
$$;

revoke all on function public.event_stats(text) from public;
grant execute on function public.event_stats(text) to anon, authenticated;

-- ===========================================================================
-- record_order — lets the prototype log an "unlock" without a payments
-- provider. Replace the body with a Stripe webhook when there is one.
-- ===========================================================================

create or replace function public.record_order(
  p_event_slug text, p_bib text, p_kind text,
  p_photo_id uuid default null, p_amount numeric default null
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare v_event uuid; v_id uuid;
begin
  select id into v_event from public.events where slug = p_event_slug and published;
  if v_event is null then return null; end if;
  insert into public.orders (event_id, bib, kind, photo_id, amount_eur)
  values (v_event, regexp_replace(p_bib, '\D', '', 'g'), p_kind, p_photo_id, p_amount)
  returning id into v_id;
  return v_id;
end;
$$;

revoke all on function public.record_order(text, text, text, uuid, numeric) from public;
grant execute on function public.record_order(text, text, text, uuid, numeric) to anon, authenticated;

-- ===========================================================================
-- Storage buckets
-- ===========================================================================

insert into storage.buckets (id, name, public)
values ('race-previews', 'race-previews', true)
on conflict (id) do update set public = true;

insert into storage.buckets (id, name, public)
values ('race-originals', 'race-originals', false)
on conflict (id) do nothing;

drop policy if exists "previews are public" on storage.objects;
create policy "previews are public" on storage.objects
  for select using (bucket_id = 'race-previews');
