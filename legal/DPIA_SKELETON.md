# Data Protection Impact Assessment (DPIA) — Skeleton

> **DRAFT for review — not legal advice.** A DPIA is likely **mandatory** here
> (GDPR Art. 35): large-scale processing of images of identifiable people with
> systematic identification. Complete this with your DPO/counsel before launch.

## 1. Description of the processing
- **Nature:** ingest event photographs, detect bib numbers by OCR, link each
  photo to a runner by bib, and let a runner retrieve their photos after
  verifying bib + date of birth. Optional paid download of originals.
- **Scope:** ~[N] photos and ~[N] runners per event; data subjects are runners
  and any bystanders captured in frame.
- **Context:** public sporting event; official race photography.
- **Purposes:** let runners find/buy their photos; §3 of the Privacy Policy.
- **Data:** name, DOB, bib, gender/category, club, nationality, results;
  photographs; order records. **No facial recognition or biometric templates.**

## 2. Necessity & proportionality
- Lawful basis: legitimate interest for publication (with LIA), contract for
  sales. Data minimisation: [justify holding DOB — it is the identity gate;
  otherwise drop it]. Retention: [N months]. Transparency: Privacy Policy +
  in-context notices.

## 3. Data flows / recipients
Timing provider → our DB (Supabase). Photos → Storage. OCR: local, with an
optional cloud fallback to Anthropic (US) — a Chapter V transfer (see the
transfer assessment). Delivery: Cloudflare. Payments: [provider].

## 4. Risks to data subjects and mitigations

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Bib enumeration exposes a runner's PII + photos | was High | High | **Mandatory bib + DOB gate; generic "no match"; fuzzy floored at 3+ digits** (implemented) |
| Wrong-runner fuzzy match surfaces a stranger's photo | Medium | High | Fuzzy floored at 3+ digits; match_kind shown; takedown path |
| Unpaid access to private originals | was High | Medium | `original_path` no longer sent to anon; signing gated server-side on a verified order (to implement in the Edge Function) |
| Bystanders who did not opt in | Medium | Medium | Objection/takedown path; consider blurring non-subject faces |
| International transfer to US OCR | Medium | Medium | SCCs/TIA, or use the offline model |
| Minors' images published | Medium | High | [Exclude minor races from public search / guardian process] |
| Data breach | Low | High | RLS deny-all on PII; service-role key server-only; breach runbook |

## 5. The facial-recognition gate (forward-looking)
The current design is **bib-only** and stays out of Art. 9. **Any** future use
of face detection/embeddings to disambiguate runners would process biometric
special-category data and requires: a fresh DPIA, an Art. 9(2) basis (realistically
explicit consent), and sign-off from counsel. Until then this is prohibited by
design and documented as such.

## 6. Outcome
[Record the residual risk rating and the DPO's/decision-maker's sign-off, or a
consultation with AZOP if residual high risk cannot be mitigated (Art. 36).]
