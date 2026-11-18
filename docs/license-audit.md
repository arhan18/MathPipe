# License Audit — commercial production gate (§9, §58)

**Rule:** nothing enters the paid production path until code license + model-weight
license + commercial terms are all recorded here. Unknown = not approved.

## Production dependencies (approved)

| Component | Version | Code license | Commercial status |
|---|---|---|---|
| Next.js / React | package.json | MIT | Approved |
| pypdf | requirements.txt | BSD-3 | Approved |
| pdfplumber / pdfminer.six | requirements.txt | MIT | Approved |
| Pillow | requirements.txt | HPND | Approved |
| python-docx | requirements.txt | MIT | Approved |
| jsonschema | requirements.txt | MIT | Approved |
| reportlab (test-only) | requirements-test.txt | BSD | Approved (never ships) |
| Supabase client libs | package.json | Apache-2.0 | Approved |
| three (frontend visual) | package.json | MIT | Approved |
| motion / lucide-react | package.json | MIT / ISC | Approved |
| Fontsource fonts (Inter, Instrument Serif, Fragment Mono) | npm | OFL 1.1 | Approved (bundle/embed allowed) |
| ThreeUI Community (`@designcodeio/threeui`) | 1.2.0 | MIT © 2026 Meng To | Approved with attribution (see below) |
| ThreeUI-authored assets in package | 1.2.0 | MIT (per ASSET-LICENSES.md) | Approved |
| ThreeUI bundled fonts | 1.2.0 | OFL 1.1 (per FONT-LICENSES.md) | Approved |

### ThreeUI vendoring note

`apps/web/components/threeui/top-dock/` vendors the modern dock variant with
content-only changes (brand, IA labels, link actions). MIT permits this;
copyright notice preserved in the file header. Divergence recorded in
`docs/ui-references.md` §1/§5.

## Candidates (NOT production-approved)

| Component | Code license | Model-weight license | Decision |
|---|---|---|---|
| Marker | Apache-2.0 | Modified OpenRAIL-M (conditions apply) | Benchmark only until exact version reviewed |
| Docling | MIT | Per-model review required | Benchmark only until reviewed |
| pix2tex weights | MIT (code) | CC BY-NC-SA | Research/prototype only |
| Nougat weights | MIT (code) | CC BY-NC | Research only |
| ThreeUI Pro components (ThreeDPaper, GlassAiButton, OrbGallery, button studies) | Not licensed to us | n/a | Not used; originals built instead |

## AI providers

No provider SDK installed; no document content routed anywhere yet. Before any
provider goes live: record terms, commercial-use permission, data
retention/training policy, and update the privacy policy to match (§42).

## Re-review triggers

Any dependency version bump, new model weight, new font/asset, or new AI
provider re-opens this file. The quality-gates `license` gate fails if this
file is missing or a gated name is unrecorded.

*Last reviewed: 2026-10-06 (scaffold stage; re-verify at beta).*
