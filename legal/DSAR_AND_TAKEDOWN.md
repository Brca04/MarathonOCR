# Data-Subject Rights: DSAR, Erasure & Photo Takedown Procedure

> **DRAFT for review — not legal advice.** Internal runbook + a spec for the
> user-facing request channel. Fill `[BRACKETED]` items.

## 1. The request channel (user-facing)

Add a working **Contact / Privacy** destination (the footer links are currently
`href="#"` — wire them to this):

- A page at `/privacy` (the Privacy Policy) and a **request form or mailto** at
  `[TAKEDOWN EMAIL]`.
- The form should capture: request type (access / correction / erasure / object
  / "remove my photo"), the bib number and date of birth (to verify identity for
  gallery-linked requests), and a free-text description. For a bystander (not a
  runner) who appears in a photo, allow the request without a bib.

## 2. Identity verification

- For a runner request tied to a bib: verify bib + date of birth match (same
  check as the search). Do not act on an unverified gallery request.
- For a photo-of-me / bystander request: verify by [describe — e.g. the
  requester identifies the specific photo URL and confirms by return email].

## 3. Response SLA

Acknowledge within [72h]; substantively respond within **one month** (GDPR
Art. 12(3)), extendable by two months for complex requests with notice.

## 4. Erasure / takedown — exact data to purge

A single runner or photo request touches all of these; do them as one
transaction so nothing is left orphaned:

1. **Storage — previews**: delete the object(s) from the `race-previews`
   bucket (`photos.preview_path`).
2. **Storage — originals**: delete the object(s) from the `race-originals`
   bucket (`photos.original_path`).
3. **`detections`**: delete rows for the affected `photo_id`(s) (this is what
   links a bib to a photo).
4. **`photos`**: delete the affected row(s).
5. **`runners`**: for a full erasure of a runner, delete/anonymise the row
   (name, dob, club, nationality). Note any legal-obligation data that must be
   retained (e.g. an order tied to a completed sale — keep the order record but
   sever it from identifying data where possible).
6. **Confirm** to the requester what was removed.

Suggested `SECURITY DEFINER` admin function (service role only — never anon),
to be called from a server context:

```sql
-- Run as service role only. Removes a runner's search linkage and photos.
create or replace function admin_erase_bib(p_event_slug text, p_bib text)
returns void language plpgsql security definer set search_path = public as $$
declare v_event uuid; v_photo record;
begin
  select id into v_event from public.events where slug = p_event_slug;
  if v_event is null then return; end if;
  -- delete detections + photos that carry this bib's detections
  for v_photo in
    select distinct p.id, p.preview_path, p.original_path
    from public.photos p
    join public.detections d on d.photo_id = p.id
    where p.event_id = v_event and d.bib_text = regexp_replace(p_bib,'\D','','g')
  loop
    -- storage objects must be removed via the Storage API from the caller,
    -- using v_photo.preview_path / v_photo.original_path, before/after this.
    delete from public.detections where photo_id = v_photo.id;
    delete from public.photos where id = v_photo.id;
  end loop;
  -- anonymise the runner row (or delete, per policy)
  update public.runners
     set full_name = '[erased]', dob = null, club = null, nationality = null
   where event_id = v_event and bib = regexp_replace(p_bib,'\D','','g');
end; $$;
```

> Storage objects are NOT deleted by SQL — the caller (an Edge Function or admin
> script using the service role) must delete `preview_path`/`original_path` via
> the Supabase Storage API as part of the same operation.

## 5. Access (DSAR) requests

Export, for a verified requester: their `runners` row, the list of photos they
appear in, and any order records — as a machine-readable file (JSON/CSV).

## 6. Objection / opt-out

Because publication relies on legitimate interest, honour objections by removing
the runner from search (steps in §4) unless a compelling overriding ground
applies (rare here). Log the objection so the row is not re-imported next sync.

## 7. Records

Keep a log of every request, the verification performed, the action taken, and
the date — this is your Art. 12 accountability evidence.
