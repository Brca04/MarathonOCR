# Licensing Decision Memo: Ultralytics (AGPL) + Anthropic Transfer

> **DRAFT for review — not legal advice.** Confirm with counsel before relying
> on any conclusion here.

## Part A — Ultralytics YOLO is AGPL-3.0

`requirements.txt` pins `ultralytics>=8.3`. Ultralytics YOLO is licensed
**AGPL-3.0**. AGPL §13 extends copyleft to software that users **interact with
over a network**: if AGPL-covered code (or a derivative) is part of a
network-served application, you may be required to offer the **complete
corresponding source** of that application under AGPL — including your own
proprietary pipeline and, arguably, the web service around it.

### The three options

1. **Buy an Ultralytics Enterprise licence.** Removes the AGPL obligation
   entirely; cleanest path if YOLO stays in the product. Cost: commercial.
2. **Keep YOLO strictly offline (recommended to evaluate first).** The README's
   target architecture already runs detection as an **offline batch** that
   writes results to the DB — the public site only ever reads Supabase and never
   invokes YOLO over the network. If YOLO is never reachable by a user over a
   network and its output (bib coordinates/text) is just data in your DB, the
   §13 "interact remotely through a computer network" trigger is not met.
   **Counsel must confirm** this severs the obligation for your exact
   deployment, and you must ensure no future feature exposes YOLO via an API.
3. **Replace the detector** with a permissively-licensed model (e.g. an
   Apache/BSD/MIT-licensed detector) if neither of the above is acceptable.

### Action items
- [ ] Decide 1, 2, or 3 (with counsel).
- [ ] Add a repository `LICENSE` (none exists today) and a `NOTICE` /
      third-party-attributions file listing all bundled OSS (Next.js, React,
      Supabase client [MIT/Apache], EasyOCR/PaddleOCR [Apache-2.0], etc.).
- [ ] If option 2: document the offline-only boundary in the DPIA and README so
      it is not accidentally broken.

## Part B — Anthropic (US) transfer for the VLM OCR fallback

`src/marathon_ocr/recognizers/engines.py` (`VLMRecognizer`) sends cropped race
images — personal data (identifiable people) — to the Anthropic API in the US.
This is a GDPR Chapter V transfer and currently has no documented safeguard.

### Options
1. **Execute Anthropic's DPA + SCCs** (or rely on their EU-US Data Privacy
   Framework certification if applicable) and record a **Transfer Impact
   Assessment**. Disclose Anthropic as a sub-processor in the Privacy Policy.
2. **Run the fallback offline** — the code comments already note swapping the
   `_call` implementation for a local Qwen2.5-VL. This **eliminates the transfer**
   and is the simplest compliance outcome; evaluate quality vs the cloud model.

### Action items
- [ ] Choose 1 or 2.
- [ ] If 1: sign the DPA, complete the TIA, add Anthropic to the sub-processor
      list and §4/§6 of the Privacy Policy.
- [ ] Confirm Supabase project **region is EU**; if not, it is the same Chapter
      V question for the whole runner PII table.
