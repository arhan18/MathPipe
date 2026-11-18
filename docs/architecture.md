# Technical Architecture — Math-Heavy PDF → Editable Word SaaS

**Status:** Proposed architecture / implementation blueprint  
**Version:** 1.3  
**Last updated:** 2026-10-06  
**Primary product:** Math-heavy PDF → high-fidelity, editable Microsoft Word (`.docx`)  
**Primary promise:** Mathematical equations become native editable Word equations; text, tables, graphs, figures, layout and document structure are preserved as faithfully as practical.

---

## 0. Purpose of This Document

This file is the master technical blueprint for the SaaS. It covers the whole product, not only the conversion engine.

It defines:

- Product/application surfaces.
- Frontend routes and page groups.
- Authentication and authorization boundaries.
- Database responsibilities.
- File/object storage.
- Conversion jobs and orchestration.
- PDF/document processing pipeline.
- Math recognition and normalization.
- Native Word equation generation.
- Table and figure reconstruction.
- DOCX generation.
- Verification and automatic repair.
- AI/provider routing.
- GPU/CPU processing strategy.
- Usage quotas and billing.
- Dodo Payments integration.
- Resend transactional emails.
- SEO/content architecture.
- Admin/operations.
- Open-source components and how they are evaluated, integrated and modified.
- Licensing/commercial-use gates.
- Testing, benchmarking and quality gates.
- Security and privacy.
- Deployment environments.
- Observability.
- Implementation order.
- Definition of done for each major subsystem.

This document intentionally avoids tying the application to a single AI vendor or a single document model. The system must be modular enough to replace an OCR model, layout model, inference provider, or GPU provider without redesigning the entire product.

---


## Architecture v1.3 Update Notes

This revision closes the remaining implementation gaps identified during architecture review, including executable MathIR packaging, explicit observability, CI/CD, migrations, authentication, upload/retention limits, and queue selection.

The following are now formally specified:

- Unique top-level section numbering with no duplicate section IDs.
- Canonical MathIR JSON Schema, versioning, validation, serialization, and mapping rules.
- Job-status REST contract, SSE event contract, reconnect semantics, and polling fallback.
- Initial GPU provider strategy, provisioning lifecycle, capacity fallback, and cost model.
- Explicit performance targets and service-level objectives (SLOs).
- Explicit variable-cost targets, per-job spend ceilings, and margin guardrails.
- Page/document quality thresholds and completed/verified/warning/failed decision rules.
- Model registry, version pinning, provenance, canary/A-B rollout, rollback, and reproducibility.
- Disaster recovery objectives, backups, retention, failover and restore tests.
- Explicit token-bucket rate limiting by route and account tier.

These are engineering targets and guardrails, not promises that every production document will meet them. They must be validated against the benchmark corpus and real usage before customer-facing SLAs are advertised.

# 1. Architecture Principles

## 1.1 Product-first architecture

The user-visible product is a complete SaaS, not a model demo.

The architecture must therefore support:

- Public marketing website.
- Conversion tool.
- Authentication.
- User dashboard.
- Conversion history.
- File lifecycle management.
- Billing.
- Usage limits.
- AI verification.
- Legal/trust pages.
- SEO pages.
- Admin/operations.

## 1.2 Math-first document reconstruction

The core problem is not generic OCR. The core problem is reconstructing a structured document from a PDF while keeping mathematical meaning and Word editability.

The system must prefer:

> PDF → structured document representation → editable DOCX

rather than:

> PDF → screenshot/image of page → DOCX

or:

> PDF → plain text → DOCX

## 1.3 Native editability is a hard requirement

Detected equations must become native Word equations whenever the system can represent them reliably.

The default path is:

`equation region → mathematical representation → OMML/Word Math → DOCX`

Flattening recognized equations into images is only a fallback for unsupported cases and must be measurable/observable.

## 1.4 Provider agnostic AI

Do not hard-code the product to one model provider.

AI calls must go through an internal abstraction:

`Verification Request → AI Router → selected provider/model`

The router can choose among:

- Cloudflare Workers AI.
- Low-cost external inference provider.
- Stronger reasoning model.
- Future self-hosted model.

## 1.5 Cost-aware inference

Use deterministic/cheap processing first and expensive inference only when necessary.

Do not send every page to an expensive model.

## 1.6 Verification over blind confidence

The system should detect uncertainty and verify suspicious regions instead of silently returning a potentially incorrect document.

## 1.7 License-safe commercial architecture

No open-source code, model weight, dataset, font, or third-party dependency may enter the paid production path until its license and commercial-use terms have been reviewed.

A repository being “open source” does not automatically mean that every model weight it distributes is commercially usable.

## 1.8 Replaceability

Every external dependency should have a clear boundary and adapter where practical.

Examples:

- `AiProvider` interface.
- `DocumentParser` interface.
- `MathRecognizer` interface.
- `DocxRenderer` interface.
- `ObjectStorage` interface.
- `BillingProvider` interface.
- `EmailProvider` interface.

---

# 2. High-Level System Architecture

```text
                                  INTERNET
                                      │
                         ┌────────────▼────────────┐
                         │   Next.js + React Web   │
                         │ Marketing + App + Tool  │
                         └────────────┬────────────┘
                                      │
                              Cloudflare Edge
                                      │
                  ┌───────────────────┼────────────────────┐
                  │                   │                    │
                  ▼                   ▼                    ▼
             Public Web         App/API Layer        Static/SEO
                                      │
                         ┌────────────▼────────────┐
                         │ Auth / Session / Access │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │       Supabase           │
                         │ Auth + Postgres + RLS    │
                         └────────────┬────────────┘
                                      │
                 ┌────────────────────┼─────────────────────┐
                 │                    │                     │
                 ▼                    ▼                     ▼
           Usage / Billing       Conversion Jobs       User Metadata
                 │                    │
                 │                    ▼
                 │             Queue / Workflow
                 │                    │
                 │          ┌─────────▼─────────┐
                 │          │ PDF Processing    │
                 │          │ Engine             │
                 │          └─────────┬─────────┘
                 │                    │
                 │     ┌──────────────┼────────────────┐
                 │     │              │                │
                 │     ▼              ▼                ▼
                 │   Text           Math             Tables/Figures
                 │   Layout         OCR              Extraction
                 │     │              │                │
                 │     └──────────────┼────────────────┘
                 │                    ▼
                 │          Structured Document Model
                 │                    │
                 │                    ▼
                 │             DOCX Reconstruction
                 │                    │
                 │                    ▼
                 │            Generated DOCX Artifact
                 │                    │
                 │                    ▼
                 │           Verification / Repair
                 │                    │
                 │          ┌─────────▼─────────┐
                 │          │ AI Provider Router│
                 │          └───────┬───────────┘
                 │                  │
                 │      ┌───────────┼────────────┐
                 │      ▼           ▼            ▼
                 │ Cloudflare     Provider B   Provider C
                 │ Workers AI
                 │
                 └────────────────────┬──────────────────
                                      ▼
                              Final DOCX + Status
                                      │
                                      ▼
                              Cloudflare R2 Storage
                                      │
                         signed/authorized download
                                      │
                                      ▼
                                    User

External services:
- Dodo Payments → billing/subscriptions/webhooks
- Resend → transactional email
- AI providers → verification/repair
```

---

# 3. Technology Baseline

## 3.1 Frontend

Primary:

- Next.js.
- React.
- TypeScript.

Use Next.js App Router unless a documented requirement forces another approach.

The product must separate:

- Server-rendered/public pages.
- Interactive authenticated application pages.
- Upload/conversion UI.
- SEO content.

## 3.2 UI/design workflow

Use the following existing workflow skills from the project:

- Taste Skill.
- Anti-Slop.
- UI/UX Pro Max.
- Three UI/component references where relevant.
- 21st.dev for component patterns/inspiration.
- GSAP only where motion adds value.
- Lenis only where smooth scrolling genuinely improves the experience.

Do not introduce animation merely to make the UI look “AI-generated”.

## 3.3 Backend/application layer

Primary edge/application platform:

- Cloudflare Workers and compatible Cloudflare services.

Use Cloudflare for:

- Edge routing.
- Lightweight API/orchestration.
- Web delivery integration.
- Queues/workflows where appropriate.
- Rate limiting and request controls where appropriate.
- Optional Workers AI inference.

Do not run heavyweight PDF/model workloads directly inside a normal short-lived HTTP request.

## 3.4 Authentication and application database

Use Supabase for:

- Authentication.
- User identity.
- PostgreSQL database.
- Row Level Security.
- Application metadata.
- Subscription state mirror.
- Usage records.
- Conversion/job metadata.
- Feedback.
- Audit metadata where appropriate.

Do not introduce a second general-purpose application database during MVP unless a concrete measured need appears.

Turso is intentionally excluded from the MVP source of truth.

## 3.5 Object storage

Preferred first implementation:

- Cloudflare R2.

Use R2 for:

- Original PDF.
- Temporary source assets.
- Extracted images.
- Generated DOCX.
- Rendered verification artifacts where needed.
- Benchmark fixtures that are permitted for storage.

Never expose raw object-storage paths directly to users. Generate authorization-controlled/signed access.

## 3.6 Payments

Use Dodo Payments for:

- Subscription checkout.
- One-time credit purchases.
- Subscription state.
- Billing events.
- Payment webhooks.
- Upgrade/downgrade state transitions.

Dodo is the payment provider; Supabase is the application source of truth for the account's current product entitlements after verified webhook processing.

## 3.7 Email

Use Resend for:

- Welcome email.
- Verification email where needed.
- Password/account notifications if the product chooses email flows outside Supabase's built-in provider.
- Conversion completed.
- Conversion failed.
- Usage warning.
- Subscription confirmation.
- Payment failure.
- Product announcements where appropriate.

Transactional email templates must be versioned.

## 3.8 AI/ML inference

Use a provider abstraction.

Candidates may include:

- Cloudflare Workers AI.
- Commercial APIs with appropriate privacy/commercial terms.
- Serverless GPU inference.
- Self-hosted open-source models whose licenses permit commercial use.

The initial provider is a configuration decision after benchmarking, not an architectural dependency.

---

# 4. Complete Product Surface

## 4.1 Public marketing site

Routes:

```text
/
/features
/pricing
/how-it-works
/faq
/about
/contact
/blog
/blog/[slug]
/guides
/guides/[slug]
/compare
/compare/[slug]
/tools
/tools/[slug]
```

The homepage must communicate the core outcome within seconds:

> Convert Math PDFs into editable Word documents.

Secondary messaging:

- Native editable equations.
- Preserve graphs/figures.
- Preserve tables.
- Preserve document structure.
- Optional verification.

## 4.2 Public conversion entry point

Route:

```text
/convert
```

Responsibilities:

- Upload.
- Validate.
- Display free/anonymous limits if applicable.
- Prompt for sign-in at the right moment.
- Choose conversion mode.
- Start conversion.
- Display status.
- Show result.

## 4.3 Authentication

Routes:

```text
/login
/signup
/forgot-password
/reset-password
```

Possible providers:

- Email/password.
- Magic link.
- Google.
- Microsoft.

The exact providers are product configuration decisions.

## 4.4 Authenticated application

Base route:

```text
/dashboard
```

Subroutes:

```text
/dashboard
/dashboard/convert
/dashboard/history
/dashboard/history/[id]
/dashboard/files
/dashboard/usage
/dashboard/billing
/dashboard/settings
```

## 4.5 Dashboard

Dashboard cards:

- Current plan.
- Conversion pages remaining.
- Verification pages remaining.
- Current billing period.
- Recent conversions.
- Start new conversion.

## 4.6 History

Each conversion record:

- Filename.
- Created timestamp.
- Page count.
- Plan/mode.
- Processing status.
- Verification status.
- Output availability.
- Download action.
- Retry if allowed.
- Delete.
- Report issue.

## 4.7 Billing

Display:

- Current plan.
- Renewal date.
- Usage.
- Upgrade/downgrade.
- Cancel.
- Credit balance.
- Purchase extra credits.
- Invoices/receipts where supported.
- Payment status.

## 4.8 Settings

Sections:

- Profile.
- Account.
- Security.
- Notifications.
- Privacy.
- Data retention.
- Delete account.

## 4.9 Legal/trust pages

Required routes:

```text
/privacy
/terms
/cookies
/security
/refund-policy
/data-processing
```

The exact set is subject to legal review.

## 4.10 Admin

Internal routes, inaccessible to ordinary users:

```text
/admin
/admin/users
/admin/jobs
/admin/conversions
/admin/usage
/admin/billing
/admin/feedback
/admin/system
/admin/licenses
```

Admin capabilities:

- User lookup.
- Job inspection.
- Failed conversion inspection.
- Usage inspection.
- Billing state inspection.
- Feedback review.
- AI/GPU cost monitoring.
- Abuse review.
- License registry.
- System health.

---

# 5. Core Conversion Pipeline

The conversion engine is the heart of the product.

## 5.1 Canonical pipeline

```text
1. Receive PDF
2. Validate upload
3. Create conversion job
4. Store original artifact
5. Inspect PDF characteristics
6. Classify document as born-digital / scanned / hybrid
7. Parse page geometry
8. Extract native text where available
9. Detect layout regions
10. Detect reading order
11. Detect equations
12. Detect tables
13. Detect figures/images
14. Detect captions and equation labels
15. Run specialized recognition only where necessary
16. Normalize recognized content
17. Build canonical Document Model
18. Generate DOCX
19. Run output validation
20. Render/check result where verification is enabled
21. Detect mismatches
22. Repair suspicious regions where safe
23. Re-check
24. Persist final DOCX
25. Update job status
26. Notify user
27. Expire/delete temporary artifacts according to retention policy
```

## 5.2 Pipeline must be staged

Do not build the entire converter as one function.

Each stage must have:

- Input contract.
- Output contract.
- Logging.
- Error classification.
- Confidence data where relevant.
- Retry policy.
- Timing measurement.
- Cost measurement where relevant.

---

# 6. PDF Ingestion Layer

## Responsibilities

- Validate PDF structure.
- Reject malformed or dangerous files.
- Determine page count.
- Determine file size.
- Inspect metadata.
- Detect encrypted/password-protected PDFs.
- Identify whether text extraction is possible.
- Identify embedded images/vector content.
- Identify whether pages appear scanned.

## Classification

Each document/page should receive a classification such as:

```text
BORN_DIGITAL
SCANNED
HYBRID
UNKNOWN
```

The initial product should optimize for `BORN_DIGITAL` math-heavy PDFs.

---

# 7. Document Understanding Layer

This layer creates structured information from the PDF.

## Subsystems

- Text extraction.
- Layout detection.
- Block segmentation.
- Reading-order detection.
- Math-region detection.
- Table detection.
- Figure detection.
- Caption detection.
- Header/footer detection.
- Equation-number detection.

The output is not the final DOCX.

The output is the internal `DocumentModel`.

---

# 8. Open-Source Component Strategy

The project should use existing open-source projects wherever they provide a good commercial/legal foundation, but we must wrap them behind our interfaces.

## 8.1 Primary candidate: Marker

Source repository:

`datalab-to/marker`

Package:

`marker-pdf`

Potential role:

- PDF parsing.
- Layout/document understanding.
- Text extraction.
- Math/inline math support.
- Table extraction.
- Image extraction.
- Reading order.
- Structured output.

Marker's current repository states that the code is Apache 2.0, while its model weights have a separate modified OpenRAIL-M licensing arrangement. Therefore, code licensing and model-weight licensing must be evaluated separately before commercial production deployment. The current README also documents GPU/CPU/MPS execution and a fast/balanced architecture. [Official repository: `datalab-to/marker`]

Use Marker as a document-understanding substrate, not as the entire product.

Potential customizations:

- Custom processor for math regions.
- Custom schema mapping.
- Custom confidence metadata.
- Custom figure extraction policy.
- Custom table normalization.
- Custom output mapper to our `DocumentModel`.
- Custom fallback routing.

Do not make our frontend directly depend on Marker output.

## 8.2 Candidate: Docling

Source repository:

`docling-project/docling`

Potential role:

- Alternative document parser.
- Benchmark candidate.
- Fallback pipeline.
- Structured document representation.
- PDF/DOCX parsing.
- Tables and layout experiments.

Docling's codebase is MIT-licensed, while individual model licenses must be checked separately. Do not assume the code license applies to every bundled model. [Official repository: `docling-project/docling`]

Docling should be benchmarked against Marker on our actual test corpus before becoming a mandatory runtime dependency.

## 8.3 Candidate: pix2tex

Source repository:

`lukas-blecher/LaTeX-OCR`

Project:

`pix2tex`

Potential role:

- Equation-region → LaTeX recognition.

The code repository is MIT-licensed, but the released pretrained model weights are licensed CC BY-NC-SA according to the project's weight-release notice. Therefore the stock pretrained pix2tex weights must be treated as **prototype/research-only until a commercial-use license is obtained or a commercially permitted replacement model/weights is selected**. [Official repository/release: `lukas-blecher/LaTeX-OCR`]

Preferred integration:

```text
Equation region
→ normalize/crop
→ pix2tex or another MathRecognizer
→ LaTeX
→ math normalization
→ confidence/equivalence checks
→ OMML
```

Do not expose pix2tex directly to users.

## 8.4 Candidate: Nougat

Source repository:

`facebookresearch/nougat`

Potential role:

- Research/benchmarking for academic PDFs.
- Potentially useful for scientific-document parsing experiments.

Current repository explicitly states:

- Code: MIT.
- Model weights: CC BY-NC.

Therefore, Nougat model weights are **not a default commercial production dependency** for this SaaS. It may be used for research/benchmarking where legally permitted, but production use requires a separate licensing decision or a different commercially permitted model. [Official repository: `facebookresearch/nougat`]

## 8.5 Other candidates

Candidates such as:

- Surya.
- Texify.
- OCR engines.
- PDFium-based rendering.
- Other math recognition models.
- Other document VLMs.

may be evaluated through the benchmark layer.

Do not add them because they are popular. Add them only when measured against our corpus and license requirements.

---

# 9. Open-Source License Gate

Before adding any open-source dependency to the commercial production path, record:

```text
Project:
Repository:
Version/commit:
Code license:
Model-weight license:
Dataset/license dependencies:
Commercial use allowed?:
Modification allowed?:
Redistribution obligations:
Attribution obligations:
Potential competitive-use restriction? :
Approved for production?:
Reviewer:
Review date:
```

## Hard rule

If the answer is unknown, the component is not approved for the paid production path.

---

# 10. Canonical Document Model

This is one of the most important architectural components.

Create an internal, product-owned representation between parsing and DOCX rendering.

Conceptual model:

```json
{
  "document": {
    "id": "...",
    "metadata": {},
    "pages": [
      {
        "pageNumber": 1,
        "width": 612,
        "height": 792,
        "blocks": [
          {
            "id": "block-1",
            "type": "paragraph",
            "bbox": [50, 100, 550, 145],
            "style": {},
            "content": "Example paragraph"
          },
          {
            "id": "eq-1",
            "type": "equation",
            "bbox": [100, 160, 500, 240],
            "latex": "\\frac{x^2+1}{x-1}",
            "confidence": 0.97,
            "number": "4"
          },
          {
            "id": "fig-1",
            "type": "figure",
            "bbox": [75, 280, 540, 520],
            "assetId": "asset-1",
            "confidence": 0.99
          }
        ]
      }
    ]
  }
}
```

The real schema should support:

- Pages.
- Bounding boxes.
- Rotation.
- Styles.
- Paragraphs.
- Headings.
- Lists.
- Equations.
- Inline math.
- Tables.
- Table cells.
- Figures.
- Captions.
- Headers.
- Footers.
- Footnotes.
- Links.
- References.
- Reading order.
- Confidence.
- Source provenance.
- Asset references.

## Why the DocumentModel exists

It decouples:

`input engine` from `output engine`.

This lets us replace Marker, Docling, pix2tex or an AI model later without rewriting the DOCX layer.

---


## 10.1 Formal MathIR contract

`MathIR` is the canonical, versioned representation of mathematical content between recognition and final Word/OMML rendering.

The canonical serialization is **UTF-8 JSON**. XML is not the authoritative storage format in MVP. If XML interoperability is required later, it must be generated from the same semantic schema rather than becoming a second source of truth.

### MathIR version

Use semantic versioning for the schema:

```text
math-ir/v1.0
```

Rules:

- Patch release: validation/clarification that does not change semantics.
- Minor release: backward-compatible optional fields or new node types.
- Major release: incompatible structural or semantic changes.
- Every persisted equation stores `schemaVersion`.
- The DOCX renderer declares the highest MathIR versions it supports.
- Readers must reject unknown major versions rather than guessing.

### Canonical JSON Schema

The production schema must be checked into the repository as a versioned file:

```text
packages/document-model/schemas/mathir/v1/math-ir.schema.json
```

The following is the authoritative shape for v1.0. The repository schema may add descriptive constraints, but it must not silently diverge from this contract.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "math-ir://schema/v1.0",
  "title": "MathIR v1.0",
  "type": "object",
  "required": ["schemaVersion", "root"],
  "properties": {
    "schemaVersion": {
      "const": "1.0"
    },
    "root": {
      "$ref": "#/$defs/node"
    }
  },
  "$defs": {
    "text": {
      "type": "object",
      "required": ["type", "value"],
      "properties": {
        "type": {"const": "text"},
        "value": {"type": "string"}
      },
      "additionalProperties": false
    },
    "node": {
      "oneOf": [
        {"$ref": "#/$defs/text"},
        {"$ref": "#/$defs/row"},
        {"$ref": "#/$defs/fraction"},
        {"$ref": "#/$defs/superscript"},
        {"$ref": "#/$defs/subscript"},
        {"$ref": "#/$defs/root"},
        {"$ref": "#/$defs/operator"},
        {"$ref": "#/$defs/function"},
        {"$ref": "#/$defs/matrix"},
        {"$ref": "#/$defs/cases"},
        {"$ref": "#/$defs/fence"},
        {"$ref": "#/$defs/accent"},
        {"$ref": "#/$defs/limit"},
        {"$ref": "#/$defs/underover"}
      ]
    },
    "row": {
      "type": "object",
      "required": ["type", "children"],
      "properties": {
        "type": {"const": "row"},
        "children": {"type": "array", "items": {"$ref": "#/$defs/node"}}
      },
      "additionalProperties": false
    },
    "fraction": {
      "type": "object",
      "required": ["type", "numerator", "denominator"],
      "properties": {
        "type": {"const": "fraction"},
        "numerator": {"$ref": "#/$defs/node"},
        "denominator": {"$ref": "#/$defs/node"}
      },
      "additionalProperties": false
    },
    "superscript": {
      "type": "object",
      "required": ["type", "base", "script"],
      "properties": {
        "type": {"const": "superscript"},
        "base": {"$ref": "#/$defs/node"},
        "script": {"$ref": "#/$defs/node"}
      },
      "additionalProperties": false
    },
    "subscript": {
      "type": "object",
      "required": ["type", "base", "script"],
      "properties": {
        "type": {"const": "subscript"},
        "base": {"$ref": "#/$defs/node"},
        "script": {"$ref": "#/$defs/node"}
      },
      "additionalProperties": false
    },
    "root": {
      "type": "object",
      "required": ["type", "radicand"],
      "properties": {
        "type": {"const": "root"},
        "degree": {"$ref": "#/$defs/node"},
        "radicand": {"$ref": "#/$defs/node"}
      },
      "additionalProperties": false
    },
    "operator": {
      "type": "object",
      "required": ["type", "symbol", "children"],
      "properties": {
        "type": {"const": "operator"},
        "symbol": {"type": "string"},
        "children": {"type": "array", "items": {"$ref": "#/$defs/node"}}
      },
      "additionalProperties": false
    },
    "function": {
      "type": "object",
      "required": ["type", "name", "arguments"],
      "properties": {
        "type": {"const": "function"},
        "name": {"type": "string"},
        "arguments": {"type": "array", "items": {"$ref": "#/$defs/node"}}
      },
      "additionalProperties": false
    },
    "matrix": {
      "type": "object",
      "required": ["type", "rows"],
      "properties": {
        "type": {"const": "matrix"},
        "rows": {
          "type": "array",
          "items": {
            "type": "array",
            "items": {"$ref": "#/$defs/node"}
          }
        }
      },
      "additionalProperties": false
    },
    "cases": {
      "type": "object",
      "required": ["type", "cases"],
      "properties": {
        "type": {"const": "cases"},
        "cases": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["expression", "condition"],
            "properties": {
              "expression": {"$ref": "#/$defs/node"},
              "condition": {"$ref": "#/$defs/node"}
            },
            "additionalProperties": false
          }
        }
      },
      "additionalProperties": false
    },
    "fence": {
      "type": "object",
      "required": ["type", "left", "right", "child"],
      "properties": {
        "type": {"const": "fence"},
        "left": {"type": "string"},
        "right": {"type": "string"},
        "child": {"$ref": "#/$defs/node"}
      },
      "additionalProperties": false
    },
    "accent": {
      "type": "object",
      "required": ["type", "kind", "child"],
      "properties": {
        "type": {"const": "accent"},
        "kind": {"type": "string"},
        "child": {"$ref": "#/$defs/node"}
      },
      "additionalProperties": false
    },
    "limit": {
      "type": "object",
      "required": ["type", "base", "lower", "upper"],
      "properties": {
        "type": {"const": "limit"},
        "base": {"$ref": "#/$defs/node"},
        "lower": {"$ref": "#/$defs/node"},
        "upper": {"$ref": "#/$defs/node"}
      },
      "additionalProperties": false
    },
    "underover": {
      "type": "object",
      "required": ["type", "base", "under", "over"],
      "properties": {
        "type": {"const": "underover"},
        "base": {"$ref": "#/$defs/node"},
        "under": {"$ref": "#/$defs/node"},
        "over": {"$ref": "#/$defs/node"}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### MathIR validation rules

Before an equation can enter DOCX generation:

1. The MathIR JSON must pass JSON Schema validation.
2. Recursive structures must be acyclic and depth-limited.
3. Matrices must have rectangular row/column shape unless the renderer explicitly supports ragged structures.
4. Every referenced node must be valid for its parent node type.
5. Text nodes must be valid Unicode.
6. Operators and functions must come from the approved symbol/function registry or be explicitly marked as custom.
7. Renderer support must be checked before claiming native editability.
8. The MathIR hash and schema version must be stored with the equation artifact.

### Serialization

Use canonical JSON serialization for hashes and deterministic regression tests:

- UTF-8.
- Stable key ordering.
- No insignificant whitespace.
- Numeric normalization.
- UTF-8-safe escaping.

The canonical serialized form is used to produce a content hash for caching and provenance.

### Mapping rules

#### LaTeX → MathIR

Parse LaTeX into an AST or parser-native tree, then normalize into MathIR.

Do not perform direct string replacement such as:

```text
LaTeX string → OMML string
```

Unsupported commands must produce a typed `unsupported` diagnostic rather than silently disappearing.

#### MathML → MathIR

Parse MathML semantics/presentation into MathIR nodes. Where MathML contains concepts without a direct v1 node, preserve the source fragment in provenance metadata and use a safe fallback.

#### MathIR → OMML

Use a deterministic renderer:

```text
fraction    → m:f
superscript → m:sSup
subscript   → m:sSub
root        → m:rad
matrix      → m:m
fence       → m:d
operator    → m:r / m:func / appropriate OMML construct
```

The mapping table must live in code and be tested against Word-rendered fixtures.

#### MathIR → LaTeX

Provide a deterministic serializer for debugging, benchmarks and user-facing LaTeX export later. This is not the source of truth.


## 10.2 MathIR repository artifact gate

The architecture package includes an executable companion schema:

```text
math-ir.schema.json
```

It MUST be copied into the repository at:

```text
packages/document-model/schemas/mathir/v1/math-ir.schema.json
```

### Pre-Phase-6 gate

The Math Engine phase cannot begin until CI confirms:

```text
schema file exists
        ↓
JSON parses
        ↓
Draft-2020-12 schema validation succeeds
        ↓
representative MathIR fixtures validate
        ↓
invalid fixtures fail validation
        ↓
schema hash is recorded
```

### Fixtures

Create:

```text
packages/document-model/schemas/mathir/v1/fixtures/
  fraction.json
  matrix.json
  superscript.json
  subscript.json
  root.json
  cases.json
  integral.json
  limit.json
  mixed-expression.json
  invalid-unknown-node.json
  invalid-ragged-matrix.json
```

The fixture set is part of the executable contract.


# 11. Math Processing Engine

## 11.1 Math detection

First identify mathematical regions.

Possible sources of evidence:

- Text/font patterns.
- PDF coordinates.
- Layout model.
- Math-specific classifier.
- Mathematical symbol density.
- VLM/ML classifier.

## 11.2 Math recognition

For recognized math regions:

```text
PDF equation region
→ clean/crop
→ MathRecognizer
→ LaTeX/MathML/structured math
→ normalize
→ validate
→ confidence score
```

## 11.3 Normalization

Normalize common representation differences:

- Whitespace.
- Equivalent LaTeX commands.
- Unicode vs LaTeX symbols.
- Font macros.
- Delimiter variants.
- Matrix syntax.
- Alignment markup.

## 11.4 Mathematical equivalence

Where practical, perform deterministic normalization and structural comparison before invoking an expensive AI model.

For example, compare the parse tree/normalized form rather than only comparing strings.

Do not claim symbolic equivalence where the implementation has not been validated.

## 11.5 Equation numbering

Store equation numbers as metadata linked to the equation block rather than as unrelated text.

---

# 12. Native Word Equation Generation

## Requirement

The output equation must be editable in Word.

Preferred route:

```text
LaTeX/MathML/structured math
→ equation AST/normalized representation
→ OMML
→ DOCX XML
```

The equation renderer should be a dedicated module:

```text
packages/docx-engine/
  math/
    omml/
    serializer/
    tests/
```

Do not rely on a screenshot of the equation for the normal path.

## Acceptance test

For supported equations:

1. Generated DOCX opens in Microsoft Word.
2. Equation can be selected.
3. Equation can be edited.
4. Equation structure survives save/reopen.
5. No image is substituted.

Maintain a corpus of equations covering:

- Fractions.
- Nested fractions.
- Roots.
- Integrals.
- Limits.
- Summation/product.
- Matrices.
- Piecewise functions.
- Superscripts/subscripts.
- Greek symbols.
- Derivatives.
- Multi-line equations.
- Numbered equations.

---

# 13. Table Reconstruction Engine

Pipeline:

```text
Detected table
→ grid detection
→ row/column structure
→ cell boundaries
→ merged-cell inference
→ cell content recognition
→ math recognition inside cells
→ Word table creation
```

Requirements:

- Row/column count.
- Merged cells.
- Header rows.
- Multi-line cells.
- Math inside cells.
- Approximate borders.
- Alignment.
- Caption association.

Tables should become native Word tables whenever confidence is sufficient.

---

# 14. Figure/Image Engine

Figures include:

- Graphs.
- Diagrams.
- Charts.
- Plots.
- Illustrations.
- Embedded raster images.

Primary target:

> preserve visual fidelity, not necessarily editability.

Preferred strategies:

1. Extract original embedded image where possible.
2. For vector-only regions, render at appropriate resolution.
3. Insert into DOCX with preserved aspect ratio.
4. Maintain approximate page position.

Store each asset with:

- asset ID.
- source page.
- bounding box.
- original format where available.
- derived format.
- checksum.
- resolution.

---

# 15. Layout and Reading Order

Support:

- One column.
- Two columns.
- Multi-column academic papers.
- Sidebars.
- Figure/caption relationships.
- Table/caption relationships.
- Headers/footers.
- Lists.
- Section hierarchy.

The internal model must preserve both:

- geometric position.
- logical reading order.

These are different concepts and should not be conflated.

---

## 15.1 Two-Column and Complex Reading Order

Two-column reading order is a dedicated subsystem, not an incidental layout rule.

The document model must store at least:

- page coordinates
- block bounding boxes
- detected column regions
- block-to-column assignment
- logical reading-order index
- figure/table interruptions

### Required strategy

```text
Page
 ↓
Detect column candidates
 ↓
Estimate column boundaries
 ↓
Assign blocks to columns
 ↓
Resolve spanning blocks
 ↓
Handle figures/tables that interrupt columns
 ↓
Construct logical reading order
```

### Special cases

Benchmark and explicitly test:

- two columns with equations
- two columns with figures
- full-width title followed by columns
- a figure spanning both columns
- a table spanning both columns
- footnotes
- headers/footers
- equations that span a column
- sidebars and callout boxes

The visual x-coordinate alone must never determine document reading order.

# 16. DOCX Reconstruction Engine

Responsibilities:

- Create `.docx` package.
- Create document styles.
- Create paragraphs.
- Create headings.
- Create lists.
- Insert native equations.
- Insert tables.
- Insert images.
- Insert captions.
- Preserve page/section structure.
- Handle headers/footers.
- Maintain bookmarks/links if supported.

Conceptual mapping:

```text
paragraph      → Word paragraph
heading        → Word heading
inline math    → Word math run
block equation → OMML block
figure         → Word drawing/image
caption        → caption paragraph/style
list           → Word numbering
link           → Word hyperlink
page break     → Word page break
section        → Word section
```

The DOCX engine must not know which upstream parser produced the data.

---

# 17. Fidelity Strategy

There are two kinds of fidelity:

## 17.1 Semantic fidelity

- Same text.
- Same mathematical meaning.
- Same tables.
- Same figures.
- Same reading order.

## 17.2 Visual fidelity

- Similar fonts.
- Similar spacing.
- Similar page breaks.
- Similar image positions.
- Similar column layout.

The product promise is:

> High-fidelity editable reconstruction.

Do not make an absolute “pixel-perfect” claim until benchmark data demonstrates it.

---

# 18. Verification and Repair Engine

This is a premium differentiator and a first-class architecture component.

## 18.1 Basic flow

```text
Original PDF
     │
     ├───────────────┐
     │               │
     ▼               ▼
Source analysis   Generated DOCX
                     │
                     ▼
               Render/check output
                     │
                     ▼
              Region comparison
                     │
                     ▼
               Issue detection
                     │
             ┌───────┴────────┐
             │                │
             ▼                ▼
          No issue         Issue found
                              │
                              ▼
                        Repair candidate
                              │
                              ▼
                          Re-render
                              │
                              ▼
                           Re-check
```

## 18.2 Verification dimensions

Check:

- Text presence.
- Equation presence.
- Equation structure.
- Table presence.
- Figure presence.
- Reading order.
- Major layout deviations.
- Equation numbering.
- Missing blocks.

## 18.3 AI should be selective

Do not send every page to a high-cost model.

Use:

```text
high confidence → skip
medium confidence → cheap verification
low confidence → stronger verification
known mismatch → targeted repair
```

## 18.4 Repair limits

Every job must have a hard retry/repair budget.

Example initial policy:

- Maximum 2 repair attempts per suspicious region.
- Maximum verification time/job.
- Maximum AI spend/job.
- Maximum total model calls/job.

These values are configurable and should be tuned using real cost/quality measurements.

---

# 19. AI Provider Router

Create an internal interface:

```text
AiProvider
  - name
  - capabilities
  - cost metadata
  - available
  - verify(request)
  - repair(request)
```

Router inputs:

- Task type.
- Document type.
- Required confidence.
- Token/context estimate.
- Provider availability.
- Daily free allocation remaining.
- Estimated cost.
- User plan.
- Latency requirement.

Router output:

```text
SelectedProvider
SelectedModel
EstimatedCost
Reason
```

## 19.1 Cloudflare Workers AI

Workers AI is one possible backend.

Current Cloudflare pricing documentation states that Workers AI has a 10,000-neuron daily free allocation and paid usage beyond that on Workers Paid. This should be treated as a cost optimization, not a mandatory provider lock-in.

Use free capacity when appropriate.

When exhausted:

- Continue using Cloudflare if it remains best price/performance.
- Or route to another approved provider.

## 19.2 External provider fallback

The router should be able to use another approved provider if:

- Cloudflare is out of allocation.
- Cloudflare model quality is insufficient for the task.
- Another provider is cheaper for the specific task.
- Latency requirements favor another provider.
- Provider availability changes.

## 19.3 Self-hosted inference

Future option for high-volume workloads.

Do not introduce it until real usage justifies the operational complexity.

---

# 20. CPU/GPU Workload Strategy

## CPU-first

Use CPU for:

- file validation.
- metadata extraction.
- basic PDF inspection.
- deterministic transformations.
- simple text extraction.
- DOCX packaging where practical.
- non-ML comparisons.

## GPU when necessary

Use GPU for:

- layout model.
- OCR model.
- complex math recognition.
- VLM inference.
- difficult scanned documents.

## Scale-to-zero goal

Do not maintain an idle expensive GPU server during periods of no work.

Conceptual lifecycle:

```text
No jobs
→ no GPU worker

Job arrives
→ provision/activate worker

Process job
→ store result

Worker idle
→ scale down/terminate
```

---


## GPU provisioning strategy

### Initial production candidate: RunPod Serverless

Use **RunPod Serverless** as the first GPU execution candidate for custom document/math inference because it supports containerized inference endpoints, autoscaling and per-second billing. Current published pricing lists a 24 GB tier including L4/A5000/3090 at approximately **$0.69/hour** for Serverless, with billing from worker start to stop and scale-to-zero flex workers. [Verify current pricing before deployment.] 

This is a deployment choice, not a permanent vendor lock. Modal is the first fallback benchmark; its current published L4 price is approximately **$0.000222/second (~$0.80/hour)**. Benchmark both using the same container and workload before production.

### Provisioning flow

```text
Queue receives GPU-required task
        ↓
Scheduler checks:
  - job budget
  - provider health
  - available capacity
  - model version
        ↓
Select provider + worker class
        ↓
Invoke serverless endpoint with job/chunk ID
        ↓
Worker pulls immutable input artifacts
        ↓
Run inference
        ↓
Write artifacts + metrics
        ↓
Acknowledge job stage
        ↓
Worker becomes idle / scales down
```

### Worker packaging

Each GPU worker is an immutable container containing:

- exact model version
- exact runtime/dependency lockfile
- model checksum
- processor version
- health-check command
- maximum request duration
- memory/VRAM limits

### Initial capacity policy

Start with one concurrent heavy GPU task per worker to avoid VRAM contention. Increase concurrency only after benchmark evidence shows stable quality and memory behavior.

### Provider fallback

```text
Primary: RunPod Serverless
          ↓ unavailable / unhealthy
Fallback: Modal
          ↓ unavailable
Queue with bounded retry
          ↓
CPU-only fallback where product quality permits
          ↓
Otherwise fail safely with user-visible retry message
```

Do not retry indefinitely across providers.

### GPU budgets

Every job gets:

- maximum GPU seconds
- maximum worker attempts
- maximum provider spend
- maximum queue wait

These values are stored in the job record and enforced server-side.

### Why not keep a GPU always running?

The product's early workload is bursty. Keeping a large GPU warm while no jobs exist is inconsistent with the pay-only-when-used business model. A warm pool may be introduced later only if latency data shows that cold starts materially hurt conversion completion time and the added idle cost is justified.

# 21. Queue and Job Architecture

Conversion must be asynchronous.

## Job lifecycle

```text
UPLOADED
VALIDATING
QUEUED
ANALYZING
PARSING
RECOGNIZING
RECONSTRUCTING
VERIFYING
REPAIRING
FINALIZING
COMPLETED
FAILED
CANCELLED
EXPIRED
```

Each job has:

- job ID.
- user ID.
- source file ID.
- page count.
- requested mode.
- plan.
- priority.
- retry count.
- started timestamp.
- completed timestamp.
- error code if failed.
- cost metadata.

## Idempotency

Every processing stage must be safe to retry.

A repeated queue delivery must not create duplicate billing or duplicate output artifacts.

---


## 21.1 Job status API contract

The browser never owns the conversion state. The server owns the durable job state.

### Create job

```http
POST /api/v1/jobs
Content-Type: application/json
Authorization: Bearer <session>
Idempotency-Key: <uuid>
```

Request:

```json
{
  "sourceFileId": "file_123",
  "mode": "standard",
  "pageRange": null
}
```

Response:

```json
{
  "apiVersion": "1",
  "job": {
    "id": "job_123",
    "state": "queued",
    "stage": "queued",
    "updatedAt": "2026-10-06T00:00:00Z"
  }
}
```

### Get job snapshot / polling fallback

```http
GET /api/v1/jobs/{jobId}
Authorization: Bearer <session>
```

Response:

```json
{
  "apiVersion": "1",
  "job": {
    "id": "job_123",
    "state": "processing",
    "stage": "reconstructing",
    "sequence": 18,
    "updatedAt": "2026-10-06T00:01:12Z",
    "progress": {
      "known": false,
      "completed": null,
      "total": null
    },
    "warningCount": 0,
    "errorCode": null
  }
}
```

The API must not invent percentages. If measured work units are available, `known=true` and `completed/total` can be provided. Otherwise the UI must show stage status only.

### SSE endpoint

```http
GET /api/v1/jobs/{jobId}/events
Authorization: Bearer <session>
Accept: text/event-stream
Last-Event-ID: <sequence>
```

Content type:

```text
text/event-stream
```

Events:

```text
job.snapshot
job.stage
job.warning
job.completed
job.failed
heartbeat
```

Event payload envelope:

```json
{
  "apiVersion": "1",
  "sequence": 19,
  "jobId": "job_123",
  "type": "job.stage",
  "occurredAt": "2026-10-06T00:01:13Z",
  "state": "processing",
  "stage": "reconstructing",
  "progress": {
    "known": false,
    "completed": null,
    "total": null
  },
  "message": "Reconstructing Word document"
}
```

### Completion event

```json
{
  "apiVersion": "1",
  "sequence": 24,
  "jobId": "job_123",
  "type": "job.completed",
  "occurredAt": "2026-10-06T00:03:22Z",
  "state": "completed",
  "stage": "finalizing",
  "artifactId": "artifact_docx_123",
  "quality": {
    "status": "verified",
    "warningCount": 0
  }
}
```

### Failure event

```json
{
  "apiVersion": "1",
  "sequence": 25,
  "jobId": "job_123",
  "type": "job.failed",
  "occurredAt": "2026-10-06T00:03:40Z",
  "state": "failed",
  "stage": "verifying",
  "errorCode": "PROCESSING_TIMEOUT",
  "retryable": true,
  "message": "The conversion exceeded the processing time limit."
}
```

### Reconnection strategy

- The client stores the highest received `sequence`.
- On reconnect, send `Last-Event-ID`.
- Server replays events after that sequence if still available.
- If events are no longer available, server sends `job.snapshot` and the client reconciles state from the authoritative snapshot.
- Heartbeat every 15–30 seconds when active.
- Client reconnects with exponential backoff: 1s, 2s, 4s, 8s, capped at 30s.

### Polling fallback

If SSE is unavailable or repeatedly disconnected:

- Poll every 3 seconds for the first 30 seconds.
- Then every 5 seconds for the next 2 minutes.
- Then every 10 seconds until 10 minutes.
- Then every 30 seconds until terminal state.
- Stop after terminal state.
- Immediately resume SSE if the browser regains a usable connection and the feature is supported.

The polling response uses the exact same job snapshot schema as the SSE `job.snapshot` event.

### Authorization

Every job-status request must verify that the authenticated principal owns the job or is an authorized member of the owning organization.


## 21.2 Queue provider selection

### Primary MVP queue

Use **Cloudflare Queues** for application/job orchestration.

Reasons:

- integrates directly with Cloudflare Workers;
- asynchronous processing;
- buffering and batching;
- retries and delays;
- dead-letter queues;
- can support pull consumers for infrastructure outside Cloudflare Workers.

Official documentation:
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/

### Queue topology

```text
conversion-create queue
        ↓
document-analysis queue
        ↓
document-process queue
        ↓
docx-build queue
        ↓
verification queue
        ↓
finalize queue
```

The exact number of queues may be reduced in MVP if operational complexity becomes unnecessary. The logical stages remain distinct even when they share a physical queue.

### Dead-letter handling

Every production queue consumer must define a DLQ. Failed messages move to the DLQ after the configured retry limit instead of being silently lost.

### External processor

Cloudflare Queues may use a pull-based consumer to hand work to the Python CPU/GPU processing system. This keeps queue orchestration separate from heavy document processing.

### Queue message contract

Messages contain only IDs and bounded metadata:

```json
{
  "schemaVersion": "1",
  "jobId": "job_123",
  "stage": "math-recognition",
  "attempt": 1,
  "sourceArtifactId": "artifact_123",
  "priority": "normal",
  "createdAt": "2026-10-06T00:00:00Z"
}
```

Do not place PDF bytes or large document payloads directly in queue messages.


# 22. File Storage Lifecycle

```text
Upload
 ↓
Original PDF stored
 ↓
Temporary extraction assets
 ↓
Intermediate outputs
 ↓
Final DOCX
 ↓
User download
 ↓
Retention timer
 ↓
Automatic cleanup
```

Each file must have:

- owner.
- purpose.
- creation time.
- expiration time.
- storage key.
- content type.
- checksum.
- size.

Temporary artifacts must expire sooner than user-visible history files.

---


## 22.1 File upload limits by plan

These are the initial product limits and can be changed by entitlement configuration without code rewrites.

| Plan | Max PDF size | Max pages/job | Max concurrent jobs |
|---|---:|---:|---:|
| Anonymous | 10 MB | 10 | 1 |
| Free | 25 MB | 25 | 1 |
| Pro | 50 MB | 150 | 3 |
| Power | 100 MB | 500 | 5 |
| Business | 250 MB | 1,000* | configurable |

`*` The 1,000-page Business limit is a product guardrail, not a promise that every 1,000-page file will finish under the normal SLO. Large jobs must still pass the job time, memory and spend budgets.

### Enforcement

Limits are enforced:

1. before upload when metadata is known;
2. after upload when actual size/page count is known;
3. before job creation;
4. before expensive processing stages.

The UI must display the applicable limits before the user begins expensive processing.


# 23. Supabase Data Model

Recommended conceptual tables:

```text
profiles
plans
subscriptions
usage_periods
usage_events
conversion_jobs
conversion_artifacts
conversion_pages
verification_runs
verification_issues
billing_events
notifications
feedback
admin_events
```

Potential relationships:

```text
user
 ├── profile
 ├── subscriptions
 ├── usage_periods
 ├── conversion_jobs
 │      ├── artifacts
 │      ├── pages
 │      └── verification_runs
 ├── notifications
 └── feedback
```

## 23.1 Source of truth

Supabase/Postgres is the source of truth for application state.

Dodo is the source of truth for payment events.

The application must update subscription entitlements only after validating Dodo events.

## 23.2 RLS

Enable Row Level Security for user-owned data.

Default rule:

> A user can only read/write rows they are authorized to access.

Admin access should be explicit and separately protected.

Do not expose service-role credentials to browsers.

---


## 23.3 Production data migration strategy

All schema changes are version-controlled migrations.

Do not modify the production database manually outside an approved migration workflow.

Supabase supports migration files and preview/branch environments; use those capabilities where the selected plan supports the required branching workflow. Official references:
- https://supabase.com/docs/guides/deployment/database-migrations
- https://supabase.com/docs/guides/deployment/branching

### Expand/contract rule

For production schema changes:

```text
Migration N
  ↓
EXPAND
Add nullable/new fields/indexes/tables
  ↓
Deploy application version that supports old + new schema
  ↓
Backfill asynchronously
  ↓
Verify metrics
  ↓
CONTRACT
Remove/deprecate old fields only after all readers/writers have moved
```

### Rules

- No migration may require application downtime unless explicitly approved.
- New code must remain compatible with the previous schema during the transition window.
- Destructive changes require at least one prior deploy that removes application dependence on the old structure.
- Large backfills run asynchronously in bounded batches.
- Every migration has an estimated lock/latency impact reviewed before production.
- Production migration order is deterministic and recorded in repository history.
- Migration status must be observable and alertable.

### Data backfill

For large tables:

```text
read batch
 → transform
 → write batch
 → checkpoint
 → repeat
```

Never load an entire table into application memory for migration.


# 24. Usage/Quota Engine

Usage is a product feature and a cost-control boundary.

Track:

- conversion pages.
- verified pages.
- extra credits.
- current billing period.
- daily limits.
- job concurrency.
- file-size limits.
- retry budget.

## Metering event

Every chargeable event should generate an internal usage event.

Example:

```text
conversion_page_consumed
verification_page_consumed
extra_credit_consumed
```

Usage must be auditable.

Do not rely only on a mutable “remaining pages” counter.

Maintain an append-only event trail and derive/aggregate balances.

---

# 25. Pricing Entitlement Model

Initial proposed plans:

```text
FREE
- 10 conversion pages/month
- 0 verified pages

PRO
- 500 conversion pages/month
- 50 verified pages/month

POWER
- 1,500 conversion pages/month
- 150 verified pages/month

HEAVY/BUSINESS
- 5,000+ conversion pages/month
- 500+ verified pages/month
```

These are starting product limits, not hard-coded infrastructure assumptions.

The actual quotas must be adjustable through configuration without changing application code.

## Lifetime plans

If offered, lifetime access must use finite credits.

Do not offer unlimited lifetime compute.

---

# 26. Dodo Payments Integration

## Responsibilities

Dodo handles:

- Checkout.
- Subscription billing.
- One-time purchases.
- Payment events.
- Subscription lifecycle events.

Application handles:

- Product entitlement state.
- Plan display.
- Usage limits.
- Credit balance.
- UI gating.

## Webhook flow

```text
Dodo event
 ↓
Webhook endpoint
 ↓
Verify signature/authenticity
 ↓
Idempotency check
 ↓
Persist billing event
 ↓
Update subscription/entitlement
 ↓
Record audit event
 ↓
Return success
```

Never trust a client-side payment success message as the entitlement source.

---

## 26.1 Webhook Reliability, Ordering and Reconciliation

External webhook delivery is eventually consistent and must be treated as unreliable transport.

Required protections:

1. Verify provider signature/authenticity.
2. Generate/require an idempotency key per provider event.
3. Persist the raw event metadata needed for audit before applying business state.
4. Make handlers idempotent.
5. Allow duplicate events.
6. Allow events to arrive out of order.
7. Reject stale state transitions where a newer known event already supersedes them.
8. Return success only after durable acceptance of the event.
9. Retry transient processing failures.
10. Run a periodic reconciliation job against provider state where the provider API supports it.

Canonical flow:

```text
Provider event
  ↓
Verify signature
  ↓
Event-id/idempotency lookup
  ├── Already processed → acknowledge safely
  └── New event
        ↓
     Persist event
        ↓
     Determine state transition
        ↓
     Apply transactionally
        ↓
     Record audit result
```

The same principles apply to payment and subscription events. Email webhook features are optional unless inbound email events are introduced.

# 27. Resend Email Architecture

Email events include:

```text
WELCOME
CONVERSION_COMPLETED
CONVERSION_FAILED
USAGE_WARNING
SUBSCRIPTION_STARTED
SUBSCRIPTION_RENEWED
PAYMENT_FAILED
PASSWORD/SECURITY_EVENT
```

Use a queue or background job for non-critical transactional email where possible.

Do not block conversion completion solely because an email API is temporarily unavailable.

---

# 28. Frontend State Architecture

The frontend should separate:

- Server data.
- Authentication state.
- Conversion job state.
- Upload state.
- UI-only state.
- Billing state.

Avoid duplicating server truth in many client stores.

Use server/API data as the canonical source for:

- usage.
- subscription.
- job status.
- file history.

---


## 28.1 Frontend job-status client contract

The frontend uses one authoritative job snapshot model regardless of transport:

```ts
type JobSnapshot = {
  id: string;
  state:
    | "queued"
    | "analyzing"
    | "processing"
    | "reconstructing"
    | "verifying"
    | "repairing"
    | "finalizing"
    | "completed"
    | "completed_with_warnings"
    | "failed"
    | "cancelled"
    | "expired";
  stage: string;
  sequence: number;
  updatedAt: string;
  progress:
    | { known: false; completed: null; total: null }
    | { known: true; completed: number; total: number };
  warningCount: number;
  errorCode: string | null;
};
```

Client algorithm:

```text
GET initial snapshot
  ↓
Open SSE
  ↓
Apply monotonic sequence updates
  ↓
On disconnect → reconnect with Last-Event-ID
  ↓
If replay unavailable → accept fresh snapshot
  ↓
If SSE repeatedly unavailable → polling fallback
  ↓
On terminal state → stop transport and refresh result metadata
```

The client must reject stale events whose sequence number is lower than the latest applied sequence.


# 29. Conversion Tool UX

## Initial state

Large dropzone.

Message:

> Drop your PDF here or choose a file.

Secondary:

> Best for math, physics, engineering, academic and STEM PDFs.

## Processing state

Show meaningful stages:

```text
✓ File uploaded
✓ PDF analyzed
✓ Text detected
✓ Mathematics detected
→ Reconstructing Word document
→ Verifying difficult regions
```

## Completed state

Show:

- Pages converted.
- Equations detected.
- Figures detected.
- Tables detected.
- Verification status.
- Download button.

---

# 30. Error UX

Never display technical stack traces to end users.

Use categories:

```text
FILE_INVALID
FILE_TOO_LARGE
PAGE_LIMIT_EXCEEDED
QUOTA_EXCEEDED
UNSUPPORTED_DOCUMENT
PROCESSING_FAILED
TEMPORARY_PROVIDER_ERROR
VERIFICATION_FAILED
OUTPUT_GENERATION_FAILED
```

Map each to a human-readable message.

Keep detailed diagnostics in internal logs.

---

# 31. SEO Architecture

## High-intent pages

Create useful pages around validated user intent, such as:

```text
/math-pdf-to-word
/pdf-equations-to-word
/calculus-pdf-to-word
/physics-pdf-to-word
/scientific-pdf-to-word
/editable-equations-word
/pdf-to-editable-word
```

Do not programmatically create thousands of thin near-duplicate pages.

## Content

```text
/blog/[slug]
/guides/[slug]
/compare/[slug]
```

Potential topics:

- How to convert math PDF to editable Word.
- Why generic PDF conversion breaks equations.
- How native Word equations work.
- How to preserve tables and figures.
- PDF equation recognition guides.
- Teacher/educator workflows.

SEO content must be useful and technically accurate.

---

# 32. Admin/Operations Architecture

Admin should be able to inspect:

## Users

- account.
- plan.
- usage.
- subscription.
- recent jobs.

## Jobs

- status.
- timings.
- model usage.
- cost estimate.
- failures.
- retries.

## Quality

- verification issues.
- user feedback.
- failed pages.
- equation fallback rate.

## Infrastructure

- queue backlog.
- processing latency.
- provider health.
- GPU utilization.
- storage usage.

## Economics

Track:

- cost per conversion page.
- cost per verification page.
- cost per job.
- cost/revenue by plan.
- worst-case account cost.

---

# 33. Cost Control Architecture

The SaaS must be designed around worst-case cost, not average cost.

## Hard controls

- Page limits.
- Verification limits.
- AI retry limit.
- GPU processing timeout.
- Max file size.
- Max page count/job.
- User concurrency limit.
- Provider spend guard.

## Routing rule

Prefer:

```text
Deterministic processing
→ local/open-source inference where allowed
→ free inference allocation
→ lowest-cost approved external inference
→ stronger model only when needed
```

## AI cost budget

Every job should have an estimated and actual AI cost field for observability.

---


## 33.1 Explicit cost targets

These are internal engineering targets for the initial consumer plans. They must be recalibrated after real benchmark data exists.

### Variable processing cost targets

| Metric | Initial target | Hard action if exceeded |
|---|---:|---|
| Standard conversion variable cost/page | ≤ $0.0025 average | Investigate and optimize |
| Verified incremental AI/compute cost/page | ≤ $0.010 average | Reduce routing/verification or re-price |
| Standard conversion p95 cost/page | ≤ $0.010 | Block expansion of plan limits until fixed |
| Verified incremental p95 cost/page | ≤ $0.030 | Reduce verification scope/model |
| Consumer job hard variable-cost ceiling | ≤ $2 by default | Abort/escalate safely; Business can override |
| Business job hard variable-cost ceiling | ≤ $20 by default | Abort/escalate safely; admin override required |

These figures exclude fixed corporate expenses such as salaries and general software subscriptions. Payment fees must be added separately when calculating contribution margin.

### Margin guardrails

At full included allowance, target contribution margin after payment processing and variable document/AI costs:

- Pro: ≥ 60% target; 40% is the minimum acceptable floor.
- Power: ≥ 60% target; 40% is the minimum acceptable floor.
- Business: priced from measured usage; do not launch a fixed page allowance that cannot clear the minimum margin floor.

If a plan fails the floor under a worst-case but allowed usage scenario, change the plan allowance/price before launch. Do not rely on users being inactive.

### Cost accounting

Every completed job must record:

- CPU seconds/cost estimate.
- GPU seconds/cost estimate.
- AI provider/model/cost estimate.
- storage/egress estimate where applicable.
- payment-attribution ID where applicable.
- total variable cost estimate.

Cost values must be recomputable from immutable usage events and provider pricing snapshots.

# 34. Verification Cost Strategy

Verification should be targeted.

Example:

```text
Page confidence = 0.99
→ no AI

Page confidence = 0.87
→ cheap verifier

Page confidence = 0.55
→ stronger verifier

Mismatch detected
→ targeted repair
```

Never use a high-cost model on an entire document when a 600×300 equation region can be checked instead.

---

## 34.1 Mobile Conversion Requirements

The conversion tool must remain usable on modern mobile browsers even though desktop is the primary editing environment.

### Mobile upload

- Full-width upload control.
- Large touch target.
- Native file picker support.
- Clear file-size/page-limit messaging.
- No hover-only actions.

### Mobile progress

Use compact stage-based progress:

```text
✓ Uploaded
✓ Analyzed
● Converting
○ Verifying
```

Allow the user to leave the page without cancelling the server-side job.

### Mobile recovery

After the browser is backgrounded, killed, or reopened, the app must restore the current job state by fetching the durable job record.

### Device test matrix

The release checklist must include real-device testing on at least:

- iOS Safari
- Android Chrome
- one smaller-screen device
- one larger mobile device

Test:

- upload
- conversion start
- refresh
- backgrounding
- returning to the app
- result download
- authentication re-entry
- upgrade/checkout navigation

# 35. Testing Strategy

Testing is a core architecture requirement.

## 35.1 Unit tests

Test:

- DocumentModel.
- Equation normalization.
- OMML generation.
- Table mapping.
- Bounding boxes.
- Billing entitlement calculations.
- Usage calculations.
- Webhook idempotency.

## 35.2 Integration tests

Test:

- PDF upload → job.
- Job → processor.
- Processor → DOCX.
- DOCX → verification.
- Dodo → entitlement update.
- Resend → notification.

## 35.3 End-to-end tests

Simulate:

```text
Signup
→ Upload
→ Conversion
→ Download
→ Usage decrement
→ Upgrade
→ Additional conversion
```

## 35.4 Regression benchmark

Maintain a permanent test corpus of real representative documents.

Categories:

- Algebra.
- Calculus.
- Probability.
- Statistics.
- Linear algebra.
- Physics.
- Engineering.
- Research papers.
- Two-column papers.
- Tables containing math.
- Figures.
- Equation numbering.
- Dense layouts.

---


## 35.5 Testing pyramid targets

Initial target distribution for automated test cases:

```text
Unit          ~60%
Integration   ~30%
E2E           ~10%
```

These are test-count targets, not coverage guarantees.

### Minimum coverage targets

- Core pure logic packages: **90%+ line coverage**.
- MathIR validation/normalization: **95%+ line coverage** and required branch coverage for all node types.
- Usage/entitlement/billing logic: **95%+**.
- Queue/job state transitions: **90%+**.
- DOCX/OMML serialization primitives: **90%+**.
- UI components: **70%+** where meaningful; critical interaction paths are required to have E2E coverage regardless of coverage percentage.
- Overall repository target: **80%+ line coverage** after the first production milestone.

Coverage alone does not prove document quality. Golden-corpus and render-comparison tests remain mandatory for the document engine.


# 36. Golden Benchmark Metrics

Measure for every engine/version:

- Text fidelity.
- Math recognition accuracy.
- Editable-equation success rate.
- Table reconstruction accuracy.
- Figure retention.
- Reading-order accuracy.
- Layout similarity.
- DOCX validity.
- Processing time.
- Peak memory.
- GPU time.
- AI calls.
- Cost per page.

Never replace a production model purely because a demo “looks better”.

Compare against the fixed benchmark.

---


## 36.1 Performance SLOs

These are engineering targets for born-digital PDFs under normal service capacity; they are not contractual customer SLAs until production data validates them.

### Queue SLO

- p95 queue wait: ≤ 30 seconds.
- p99 queue wait: ≤ 2 minutes.
- Large/bulk jobs may use a separate lower-priority queue.

### Standard conversion throughput target

On the benchmark baseline worker:

- p50 processing time: ≤ 5 seconds/page excluding queue and upload.
- p95 processing time: ≤ 15 seconds/page excluding queue and upload.

### Verified conversion target

For pages actually sent through verification:

- p50 additional verification time: ≤ 5 seconds/page.
- p95 additional verification time: ≤ 20 seconds/page.

### DOCX assembly target

- p95 final DOCX assembly: ≤ 10 seconds for documents up to 50 pages.
- For larger documents, assembly should scale approximately linearly and must be benchmarked separately.

### End-to-end target examples

Normal-capacity targets:

- ≤10-page standard job: p95 ≤ 3 minutes.
- ≤50-page standard job: p95 ≤ 10 minutes.
- 51–200 pages: p95 ≤ 30 minutes.
- 200+ pages: no customer-facing fixed completion promise in MVP; progress must remain observable and resumable.

If a future hardware/model change materially improves these numbers, the product may advertise a stronger target only after sustained measurement.

# 37. Core Quality KPI

Primary technical KPI:

> **Verified editable-page success rate**

Definition:

A page is successful when:

1. Required content is present.
2. Mathematical content is structurally correct to the agreed benchmark standard.
3. Required equations are editable Word equations.
4. Tables/figures are retained as required.
5. Reading order is acceptable.
6. Output DOCX is valid/openable.

---


## 37.1 Explicit quality thresholds

The product uses a quality score composed of weighted sub-scores:

```text
PageQualityScore =
  0.35 * textFidelity
+ 0.35 * mathFidelity
+ 0.10 * tableFidelity
+ 0.10 * figureFidelity
+ 0.10 * layoutAndReadingOrderFidelity
```

Weights are initial and may be tuned after benchmark calibration.

### Page thresholds

For the initial launch benchmark:

- **Verified success:** page score ≥ 0.97 and no critical content error.
- **Acceptable standard:** page score ≥ 0.95 with no critical error.
- **Warning:** page score 0.90–<0.95 or one localized non-critical issue.
- **Failed:** page score < 0.90, missing critical content, or malformed/unopenable DOCX.

### Document thresholds

- **Verified:** weighted document average ≥ 0.98 and zero critical page failures.
- **Completed with warnings:** average ≥ 0.95 with only localized/non-critical warnings.
- **Failed:** average < 0.95, any critical loss that changes meaning, or output cannot be reliably opened.

### Equation acceptance criteria

On the fixed gold corpus:

- Structural/math-equivalence accuracy target: ≥ 98% for supported equations.
- Native editable-equation rate: ≥ 99% of equations classified as supported.
- Critical equation error rate: ≤ 0.5%.
- Unsupported equations must be routed to explicit fallback rather than silently accepted.

These are benchmark acceptance criteria, not a claim that every arbitrary PDF will achieve the same result.

### Critical-error examples

A critical error includes:

- wrong mathematical operator that changes meaning;
- missing numerator/denominator;
- incorrect matrix dimensions;
- missing exponent/subscript that changes meaning;
- missing question/paragraph;
- swapped reading order in a way that changes meaning;
- lost table data;
- missing figure required to interpret nearby text;
- malformed output that Word cannot open.

# 38. Observability

Track every conversion stage.

Useful fields:

```text
job_id
user_id
stage
started_at
finished_at
duration_ms
model
provider
input_pages
output_pages
ai_calls
gpu_seconds
estimated_cost
actual_cost
error_code
retry_count
```

Do not store raw sensitive document content in logs.

---


## 38.1 Monitoring implementation

The initial monitoring stack is intentionally small and vendor-conscious.

### Primary stack

- **Sentry** for application errors, traces, performance issues, alerting and release health.
- **OpenTelemetry** for vendor-neutral tracing and metrics instrumentation across the Next.js/TypeScript application and Python processing services.
- **Cloudflare Analytics / Logs** for edge, Worker and queue-facing request telemetry.
- **Supabase dashboard/logs** for database, Auth and platform-level diagnostics.

OpenTelemetry JavaScript provides stable tracing and metrics APIs; Sentry provides Next.js/JavaScript instrumentation and supports custom span metrics and LLM/AI monitoring. See the official documentation before implementation:
- https://opentelemetry.io/docs/languages/js/
- https://docs.sentry.io/platforms/javascript/guides/nextjs/
- https://docs.sentry.io/product/llm-monitoring/getting-started/

### Required telemetry

Create a single trace across:

```text
browser request
  ↓
Next.js/API
  ↓
job creation
  ↓
Cloudflare Queue
  ↓
processor
  ↓
math recognition
  ↓
DOCX rendering
  ↓
verification
  ↓
artifact finalization
```

Propagate:

- `requestId`
- `traceId`
- `jobId`
- `userId` or organization ID only where privacy policy permits
- `modelVersion`
- `provider`
- `applicationVersion`

### Alerts

Minimum production alerts:

- conversion failure rate > 5% for 10 minutes;
- queue depth above SLO threshold for 10 minutes;
- p95 queue wait > 2 minutes;
- p95 processing time > target by 50% for 15 minutes;
- verification spend > daily budget;
- unexpected GPU spend spike;
- webhook failures > 1% for 10 minutes;
- 5xx rate > 2% for 5 minutes;
- database connection/error anomalies;
- storage operation failures;
- retention cleanup backlog > 1 hour.

### Cost-conscious rule

Do not add Datadog/Grafana/ELK as mandatory infrastructure for MVP. Add a second telemetry backend only when scale or compliance requires it.


# 39. Logging Policy

Log:

- IDs.
- Metadata.
- Stage transitions.
- Error codes.
- Timing.
- Provider name.
- Model name.
- Resource usage.

Avoid logging:

- full PDF content.
- complete equation text unless needed for debugging and privacy-approved.
- document secrets.
- access tokens.
- API keys.

Sensitive debugging samples should use controlled benchmark fixtures.

---

# 40. Security Model

## Browser

Never hold service-role or provider secrets.

## API

Validate:

- session.
- authorization.
- plan.
- quota.
- payload.
- file ownership.

## Storage

Use short-lived authorized downloads.

## Webhooks

Verify provider signature/secret.

Use idempotency.

## Database

Use RLS for user-owned rows.

## Admin

Use stronger authentication/authorization than normal users.

---

# 41. Privacy and Data Retention

The product should have a clear retention policy.

Recommended product behavior:

- Original PDFs retained only as long as necessary for the user-visible workflow/history.
- Temporary extraction artifacts deleted automatically.
- Generated DOCX retained according to product settings.
- User can delete files from history.
- Account deletion triggers data-deletion workflow.

AI-provider processing must be documented in the privacy/data-processing policy.

Do not claim “we never store/process files” unless that is technically true across every provider and processing stage.

---

## 41.1 File Retention Enforcement and Deletion Verification

Retention policy must be executable, not merely documented.

Every stored file/artifact must have:

- owner/account ID
- created time
- expiration time or retention class
- artifact type
- storage location
- deletion state

A periodic cleanup process must:

```text
Find expired artifact
  ↓
Delete object
  ↓
Verify deletion / absence where provider semantics allow
  ↓
Mark metadata deleted
  ↓
Emit audit event
```

If deletion fails, retry with backoff and alert after the retry budget is exhausted.

Account deletion must cascade through:

- source PDFs
- generated DOCX files
- intermediate artifacts
- verification artifacts
- user-visible history metadata where required by the privacy policy

Backups must be covered by a documented deletion/retention strategy appropriate to the chosen backup system.


## 41.2 Initial retention durations

The following are the initial user-visible retention targets:

| Plan | Original PDF | Generated DOCX | Intermediate artifacts | Conversion metadata/history |
|---|---:|---:|---:|---:|
| Anonymous | 24 hours | 24 hours | 2 hours | 7 days where permitted |
| Free | 7 days | 7 days | 24 hours | 30 days |
| Pro | 30 days | 30 days | 48 hours | 180 days |
| Power | 90 days | 90 days | 72 hours | 365 days |
| Business | 180 days | 180 days | 7 days | configurable |

### Important distinction

Retention of a generated DOCX in user history is separate from backup retention and operational logs.

Privacy-facing deletion must describe actual behavior, including provider-side backups where applicable.

A user-requested deletion must not be delayed until the nominal retention expiry.

### Expiration warnings

Show an in-app warning when a stored artifact is within 24 hours of expiry.

For paid users, the system may support a user-controlled "retain longer" option only if the selected plan and privacy policy support it.


# 42. AI Data-Handling Rules

Before routing document content to an external AI provider, confirm:

- Provider terms permit our use.
- Commercial use is allowed.
- Data usage/retention behavior is acceptable.
- Customer-facing privacy statement matches reality.
- Enterprise/privacy requirements are documented.

Prefer sending the smallest necessary input:

- One page.
- One region.
- One equation.
- Relevant metadata.

Do not send an entire 100-page document to a reasoning model when a single equation crop is sufficient.

---

# 43. API Boundaries

Recommended internal modules:

```text
apps/web
packages/auth
packages/db
packages/billing
packages/usage
packages/storage
packages/jobs
packages/document-model
packages/pdf-engine
packages/math-engine
packages/table-engine
packages/figure-engine
packages/docx-engine
packages/verification
packages/ai-router
packages/email
packages/observability
```

The processing runtime may be a separate Python service/workspace because the best PDF/ML ecosystem is Python-heavy.

The user-facing application remains Next.js/React/TypeScript.

---


## 43.1 API contract conventions

All public application APIs use:

- versioned paths (`/api/v1/...`)
- JSON request/response bodies unless otherwise documented
- authenticated authorization where required
- idempotency keys for create/charge/job operations
- stable machine-readable error codes
- request IDs for support/debugging
- optimistic concurrency/version fields where mutable resources can race

### Error envelope

```json
{
  "error": {
    "code": "SOME_STABLE_CODE",
    "message": "Human-readable explanation",
    "requestId": "req_123",
    "details": {}
  }
}
```

No frontend should infer business state from HTTP status alone. Use the documented `code` and authoritative resource snapshot.


## 43.2 Authentication and authorization mechanism

### Browser/web application

Use **Supabase Auth with cookie-based sessions** through `@supabase/ssr` for the Next.js App Router.

Flow:

```text
Browser
  ↓
Supabase Auth
  ↓
HTTP-only/secure session cookies as configured by the SSR integration
  ↓
Next.js server components / route handlers
  ↓
Supabase authorization + application authorization
```

The application must not store the Supabase service-role key in the browser.

Official Supabase references:
- https://supabase.com/docs/guides/auth/server-side
- https://supabase.com/docs/guides/auth/quickstarts/nextjs

### API authorization

- Browser-originated protected APIs authenticate through the Supabase session.
- Machine-to-machine APIs added later use scoped API keys or signed service credentials, never user passwords.
- Internal service-to-service requests use short-lived signed service tokens or HMAC-signed requests with key rotation.
- Admin access requires authenticated user session plus an explicit admin role/claim.
- RLS remains the database-level authorization backstop.

### SSE

SSE uses the same authenticated browser session. The server validates ownership/organization membership for the job before opening the stream.

### Service accounts

Every non-user service identity must have:

- distinct credentials;
- least privilege;
- expiration/rotation policy;
- audit metadata.


# 44. Recommended Repository Structure

```text
math-pdf-to-word/
│
├── apps/
│   ├── web/                         # Next.js + React
│   └── processor/                   # Document-processing runtime
│
├── packages/
│   ├── auth/
│   ├── db/
│   ├── billing/
│   ├── usage/
│   ├── storage/
│   ├── jobs/
│   ├── document-model/
│   ├── pdf-engine/
│   ├── math-engine/
│   ├── table-engine/
│   ├── figure-engine/
│   ├── docx-engine/
│   ├── verification/
│   ├── ai-router/
│   ├── email/
│   ├── observability/
│   └── shared/
│
├── supabase/
│   ├── migrations/
│   ├── seed/
│   └── tests/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── golden-corpus/
│   └── benchmark/
│
├── docs/
│   ├── architecture.md
│   ├── implementation-plan.md
│   ├── model-benchmark.md
│   ├── license-audit.md
│   └── operations.md
│
├── scripts/
│   ├── benchmark/
│   ├── migrations/
│   └── local-tools/
│
└── README.md
```

---

# 45. Why TypeScript + Python

Use TypeScript for:

- Next.js.
- UI.
- Browser/API contracts.
- Billing.
- Application business logic.
- User/session/entitlement flows.

Use Python where advantageous for:

- PDF processing.
- Layout models.
- Math OCR.
- ML inference.
- Image processing.
- Scientific document parsing.

Communication between application and processor must use a versioned job/document contract.

Do not directly couple random Python model internals to the web app.

---

# 46. Processor Contract

Input:

```json
{
  "jobId": "...",
  "sourceArtifactId": "...",
  "mode": "standard|verified",
  "pageRange": null,
  "limits": {
    "maxPages": 500,
    "maxVerificationPages": 50
  }
}
```

Output:

```json
{
  "jobId": "...",
  "status": "completed",
  "artifactId": "...",
  "metrics": {
    "pages": 20,
    "equations": 101,
    "figures": 12,
    "tables": 8
  },
  "quality": {
    "verifiedPages": 18,
    "issues": 2
  }
}
```

The actual contract should be versioned, for example:

`document-contract-v1`.

---

# 47. Failure Isolation

One bad page must not necessarily destroy the whole document.

Where possible:

```text
Page 1 → success
Page 2 → success
Page 3 → difficult math → targeted fallback
Page 4 → success
```

The document job should record page-level failures and only fail the whole job when the result cannot satisfy the product's minimum quality threshold.

---

# 48. Fallback Strategy

## Equation fallback

If native equation reconstruction fails:

1. Retry recognition with an alternate **commercially approved** recognizer/model.
2. Normalize/repair representation.
3. Try alternate OMML conversion.
4. If still unsupported, optionally insert image fallback and mark internally as non-editable.

The product should not silently claim every equation is editable if a fallback image was used.

## Table fallback

If reliable native table construction fails:

- Preserve the visual table as an image only if necessary.
- Flag the block internally.

## Figure fallback

Render the region as an image if original extraction is unavailable.

---

# 49. Conversion Modes

## STANDARD

Goal:

- Low cost.
- Fast processing.
- Good default quality.

## VERIFIED

Goal:

- Higher quality assurance.
- Targeted verification.
- Automatic repair.

## BATCH

Future:

- Multiple files.
- Higher concurrency.
- Organization users.

---

# 50. Free vs Paid Processing Policy

Free:

- Small page limit.
- Standard conversion.
- No expensive full-document AI verification.

Paid:

- Higher page allowance.
- Verified conversion quota.
- Larger files.
- Priority.
- Batch features as plan allows.

Do not intentionally degrade mathematical correctness for free users. Meter expensive resources instead.

---

# 51. Abuse Prevention

Defend against:

- automated upload bots.
- repeated failed jobs.
- concurrency abuse.
- oversized files.
- huge page-count PDFs.
- pathological documents designed to consume compute.
- retry storms.

Use:

- rate limits.
- quotas.
- file limits.
- concurrency limits.
- job timeouts.
- spend ceilings.
- suspicious account controls.

---


## 51.1 Explicit rate-limiting specification

Use a **token-bucket** algorithm at the edge/application boundary, backed by a shared coordination mechanism so limits apply consistently across instances.

Each bucket has:

- capacity (burst allowance)
- refill rate
- identity key
- route group
- account tier

### Initial route limits

| Route group | Anonymous | Free account | Pro | Power | Business |
|---|---:|---:|---:|---:|---:|
| Login/signup | 10/min/IP | 10/min/IP | 10/min/IP | 10/min/IP | 20/min/IP |
| Upload-init | 3/min/IP, burst 5 | 5/min/user, burst 10 | 20/min/user, burst 10 | 40/min/user, burst 20 | Configurable |
| Create conversion job | 2/min/IP | 5/min/user | 20/min/user | 40/min/user | Configurable |
| Concurrent conversion jobs | 1 | 1 | 3 | 5 | Configurable |
| Job status polling | 30/min/job | 30/min/job | 60/min/job | 120/min/job | Configurable |
| File download | 30/min/IP | 60/min/user | 120/min/user | 240/min/user | Configurable |
| Feedback/report | 5/min/IP | 10/min/user | 20/min/user | 20/min/user | 50/min/user |

These are initial safeguards and must be adjusted using abuse telemetry.

### Anonymous protection

Anonymous conversion is considered untrusted. Combine:

- IP token bucket
- daily IP conversion budget
- file-size/page-count limits
- file fingerprinting
- CAPTCHA escalation after threshold
- progressive trust after successful account verification

Never use file fingerprinting to expose document contents or identify unrelated users; it is only an abuse-control signal.

### 429 response

Rate-limited requests return:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 12
```

Body:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests. Please try again shortly.",
    "retryAfterSeconds": 12
  }
}
```

### Server-side enforcement

Client-side limits are only UX. All quotas and rate limits must be enforced server-side.

# 52. Admin Cost Dashboard

Minimum metrics:

```text
Revenue
├── MRR
├── paying users
└── average revenue/user

Processing cost
├── CPU cost estimate
├── GPU cost
├── AI cost
├── storage cost
└── email/payment cost estimate

Unit economics
├── cost/page
├── cost/verified-page
├── cost/job
└── gross margin by plan
```

This is essential because the business model is usage-based.

---

# 53. Environment Strategy

## Local

Developer machine.

Purpose:

- development.
- model experiments.
- test corpus.
- deterministic tests.

## Preview

Temporary deployment for PR validation.

## Staging

Production-like configuration with test payments and test files.

## Production

Real user data and payments.

Use separate credentials and buckets/databases for each environment.

---

# 54. Secrets Management

Never commit:

- Supabase service keys.
- Dodo keys.
- Resend keys.
- Cloudflare tokens.
- AI provider API keys.
- Storage credentials.

Use environment/secret management appropriate to the deployment platform.

Document variable names, not secret values.

Example:

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
DODO_API_KEY
DODO_WEBHOOK_SECRET
RESEND_API_KEY
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
AI_PROVIDER_PRIMARY_API_KEY
AI_PROVIDER_SECONDARY_API_KEY
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
```

---

# 55. CI/CD

Every pull request should run:

1. Type checks.
2. Lint.
3. Unit tests.
4. Contract tests.
5. Relevant integration tests.
6. Security/dependency checks.

Model-heavy benchmark tests can run on a schedule or before merges affecting the processor.

Production deploy requires all required gates to pass.

---


## 55.1 CI/CD pipeline structure

Use **GitHub Actions** as the repository CI/CD orchestrator.

Official deployment-environment reference:
https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments

### Environments

```text
local
  ↓
pull request / preview
  ↓
staging
  ↓
production
```

### Pull request pipeline

```text
Checkout
  ↓
Install/restore dependencies
  ↓
Lint
  ↓
Type check
  ↓
Unit tests
  ↓
Contract tests
  ↓
Integration tests
  ↓
Security/dependency scan
  ↓
Build web
  ↓
Build processor containers
  ↓
MathIR schema validation
  ↓
DOCX/OMML smoke fixtures
  ↓
Create preview deployment
```

### Staging pipeline

On merge to `main`:

```text
Build immutable artifacts
  ↓
Apply database migrations to staging
  ↓
Deploy web/API
  ↓
Deploy processor image
  ↓
Run smoke tests
  ↓
Run representative document tests
  ↓
Run webhook/billing sandbox tests
  ↓
Promote or block
```

### Production pipeline

Production deployment requires:

- all required CI checks green;
- staged smoke tests green;
- license gate unchanged or re-approved;
- required migrations reviewed;
- deployment approval for production environment;
- versioned application/model references recorded.

### Rollback

Rollback must support:

- application version rollback;
- processor image rollback;
- model-version rollback;
- configuration rollback.

Database rollbacks are handled through forward-fix/compatible migration patterns, not by blindly reversing destructive migrations.


# 56. Dependency Management

Pin or lock production dependencies.

Do not silently upgrade a core ML/document parser in production.

Any parser/model upgrade must trigger:

- golden corpus benchmark.
- license re-check.
- performance comparison.
- output regression comparison.

---

# 57. Benchmark-Driven Model Selection

Initial benchmark process:

```text
Collect 50–100 representative PDFs
            ↓
Run candidate engines
            ↓
Measure quality
            ↓
Measure latency
            ↓
Measure compute
            ↓
Measure cost
            ↓
Review licenses
            ↓
Select baseline
```

Candidate matrix may include:

- Marker.
- Docling.
- pix2tex.
- Other math OCR.
- Other VLM/document models.

Do not choose based only on benchmark scores published by the project owner. Include our own corpus.

---


## 57.1 Production model registry and versioning

Every inference component must be identified by an immutable model reference.

Canonical reference format:

```text
<provider>/<model>@<modelVersion>#<artifactHash>
```

Example:

```text
provider-a/math-model@2.3.1#sha256:...
```

Store, per conversion stage:

- provider
- model name
- model version
- model checksum/digest where available
- container image digest
- prompt/template version if an LLM is used
- preprocessing version
- postprocessing version
- model configuration
- benchmark score at approval time
- license approval ID

### Production pinning

Production jobs must run against pinned versions, not floating `latest` tags.

### Model registry entity

Maintain a registry record with:

```text
model_id
provider
model_name
version
artifact_digest
status: candidate|canary|production|deprecated|blocked
license_status
benchmark_run_id
approved_at
approved_by
```

### Canary rollout

New models must first run in shadow/canary mode:

```text
Existing production model
        │
        ├── serves users
        │
        └── candidate model evaluates shadow traffic
```

Compare:

- quality
- cost
- latency
- failure rate
- fallback rate

Only promote when the candidate clears the same production gates.

### A/B testing

When user-visible behavior can safely be split, use deterministic hashing on `jobId` or another non-sensitive stable identifier to assign cohorts.

Never A/B test critical billing or security behavior.

### Rollback

A rollback is a registry pointer change to the last approved version. The old model artifacts must remain available for the retention period needed to reproduce/debug active jobs.

### Reproducibility

Every generated DOCX must be traceable to the exact model and processor versions that produced it.


## 57.2 Model version registry and rollout

Every production inference call must record an immutable model reference.

Required fields:

```text
model_family
provider
model_id
model_version
weights_digest or immutable model revision
prompt/template version if applicable
processor_version
mathir_schema_version
```

### Model registry

Keep a versioned registry in source control:

```text
configs/models/
  document/
  math/
  verification/
```

Each entry defines:

- provider;
- model identifier;
- revision/version;
- capabilities;
- license status;
- benchmark score;
- expected cost;
- enabled environments.

### Rollout stages

```text
benchmark
  ↓
shadow
  ↓
canary
  ↓
limited production
  ↓
default
```

### Rollback

The previous approved version must remain deployable without rebuilding the application.

### A/B tests

A/B tests must be deterministic by stable user/job assignment, and output artifacts must record the selected variant.

No A/B model may be enabled for paid production users until:

- license gate passes;
- benchmark thresholds pass;
- cost budget passes;
- rollback is tested.


# 58. Commercial License Decision Matrix

Example template:

| Component | Code license | Model license | Commercial status | Decision |
|---|---|---|---|---|
| Marker | Apache-2.0 | Separate model license | Must review current terms | Candidate |
| Docling | MIT | Per-model review | Generally friendly code license | Candidate |
| pix2tex | MIT | CC BY-NC-SA for released pretrained weights; commercial alternative required for production | Research/prototype only until cleared | Not production-approved |
| Nougat | MIT | CC BY-NC | Not default commercial model path | Research only |
| Custom model | Company-owned | Company-owned | Commercial | Preferred long-term |

The final license audit must use the exact versions/commits we deploy.

---

# 59. Critical Risk Resolution Matrix

This section records which risks are already covered by the architecture and which require explicit implementation work. A risk marked **Architecturally covered** is not the same as “proven solved”; it means the blueprint contains a required control and an implementation task must still satisfy and test it.

| # | Risk | Current architecture status | Required implementation status |
|---|---|---|---|
| 1 | Math recognition accuracy | **Architecturally covered** | Multi-engine benchmark, confidence thresholds, structural validation, fallback, image fallback, regression corpus |
| 2 | OMML complexity | **Architecturally covered** | MathIR, deterministic OMML renderer, unsupported-construct handling, Word round-trip corpus |
| 3 | Processing cost explosion | **Architecturally covered** | Per-job budgets, selective verification, retry caps, provider routing, cost telemetry, hard stop |
| 4 | License compliance | **Architecturally covered** | Exact-version license registry and production approval gate before commercial deployment |
| 5 | 500+ page scalability | **Architecturally covered** | Page/chunk processing, bounded concurrency, checkpointing, resumability, memory profiling |
| 6 | Anonymous abuse | **Partially covered → now explicit** | IP/user rate limits, file fingerprinting, CAPTCHA escalation, anonymous daily budget, progressive trust |
| 7 | Browser refresh/close | **Partially covered → now explicit** | Server-side durable jobs, resumable status endpoint, SSE with polling fallback, completion email |
| 8 | Session expiration mid-conversion | **Partially covered → now explicit** | Job continues after authorization, result access re-authentication, clear session messaging |
| 9 | Fake progress | **Architecturally covered** | Stage-based truthful status, no fabricated percentages |
| 10 | Two-column reading order | **Partially covered → now explicit** | Column detection, column-aware reading-order algorithm, adversarial corpus and visual tests |
| 11 | File retention compliance | **Architecturally covered** | TTLs, deletion workflow, privacy disclosures, provider retention review, deletion verification |
| 12 | Webhook reliability | **Architecturally covered** | Signature validation, idempotency keys, event ledger, retry/reconciliation worker, out-of-order handling |
| 13 | AI provider lock-in | **Architecturally covered** | Strict adapter interfaces, provider-neutral request/response contracts, scheduled benchmark suite |
| 14 | Mobile conversion experience | **Partially covered → now explicit** | Responsive upload/progress UI, touch targets, mobile browser testing matrix, resume-after-background behavior |

The remaining “Partially covered” items below are promoted to explicit architecture requirements in this version.

---

# 60. Critical Risks and Required Mitigations

The following are first-class architecture requirements, not optional future improvements.

## 60.0A Anonymous Abuse and Progressive Trust

Anonymous conversion is a product decision, not a security assumption.

If anonymous conversion is enabled, the system must apply a separate anonymous-risk policy before creating expensive processing jobs.

### Anonymous request controls

At minimum track:

- Source IP/risk signal.
- Anonymous session identifier.
- File fingerprint/hash.
- Request frequency.
- Page count.
- File size.
- Processing cost estimate.
- Recent successful/failed jobs.

Do not treat IP alone as an identity because legitimate users can share IPs and attackers can rotate IPs.

### Progressive trust

Use escalating friction:

```text
First normal request
  ↓
Low-friction anonymous conversion
  ↓
Repeated/high-volume requests
  ↓
Stricter rate limit
  ↓
CAPTCHA / verification
  ↓
Account required
```

### Anonymous budget

Anonymous users must have a hard server-side daily/monthly budget independent of the visible free-plan quota.

Never allow an anonymous client to create unlimited expensive verification jobs by repeatedly refreshing or changing client-side identifiers.

### File fingerprinting

Compute a non-sensitive content fingerprint for uploaded files to help detect repeated abuse. Do not use the fingerprint as a substitute for authorization or privacy controls.

### Abuse controls

Support:

- token-bucket or equivalent rate limiting
- per-IP limits
- per-session limits
- per-file limits
- daily anonymous processing budget
- CAPTCHA escalation
- account requirement after threshold
- temporary deny/quarantine state for abusive sources

All expensive-job authorization must happen server-side.

## 60.0B Durable Jobs and Browser Independence

A conversion job must survive browser refresh, tab closure, temporary network loss, and normal client navigation.

The browser is a **viewer of job state**, not the owner of the job.

Required flow:

```text
User starts conversion
      ↓
Server creates durable job
      ↓
Job ID returned to client
      ↓
Browser subscribes to status
      ↓
Processing continues independently
      ↓
Browser may disconnect
      ↓
Job continues
      ↓
User returns
      ↓
Client fetches current job state
```

### Live updates

Preferred:

- Server-Sent Events (SSE) for one-way job updates.

Fallback:

- authenticated polling with exponential/backoff intervals.

WebSockets are optional and should not be required merely to show conversion progress.

### Completion after browser close

When a job finishes while the browser is closed:

- persist completion state
- retain the output according to retention policy
- send transactional email when the user has opted in / the plan permits it
- show the completed result immediately when the user returns

## 60.0C Session Expiration During Processing

Authentication controls access to the user's application data; it must not be the lifecycle controller for an already-authorized processing job.

Once a job has passed authorization and been created:

- processing continues independently of the browser session
- workers authenticate service-to-service using short-lived/service credentials
- the job remains owned by its original user/account ID
- output remains inaccessible to unauthorized users

If the session expires while the job is running:

```text
Session expires
    ↓
Job continues
    ↓
User is asked to sign in again
    ↓
User returns to job/result page
    ↓
Authorization checked
    ↓
Result shown if still permitted
```

The UI must clearly distinguish:

- session expiration
- conversion failure
- job still processing

Do not tell a user that the conversion failed merely because their session expired.

## 60.0D Truthful Progress and Job State

Do not fabricate percentages.

The status model must come from real persisted state transitions such as:

```text
uploading
queued
analyzing
processing
reconstructing
verifying
repairing
finalizing
completed
completed_with_warnings
failed
expired
```

If exact progress is measurable, it may be shown.

Otherwise show:

> “Reconstructing your Word document…”

rather than a made-up “73%”.

If pages/chunks are processed, it is acceptable to show truthful counters such as:

> “37 of 48 pages processed.”

---

## 60.1 Math recognition accuracy

### Risk

No single math-recognition model should be assumed to correctly recognize every mathematical expression. The stock pix2tex model reports a token-accuracy metric of about 0.60 in its project documentation, and it is an equation-image-to-LaTeX system rather than a guaranteed PDF-to-editable-Word engine. [Official project: `lukas-blecher/LaTeX-OCR`]

### Required architecture

Never use one recognizer as the unconditional source of truth.

```text
PDF page
  ↓
math-region detector
  ↓
Is this region definitely mathematics?
  ├── No → preserve as text/image according to type
  └── Yes
       ↓
Primary MathRecognizer
       ↓
Normalize representation
       ↓
Confidence + structural checks
       ↓
High confidence?
   ├── Yes → continue
   └── No
        ↓
Approved fallback recognizer / stronger model
        ↓
Re-check
        ↓
Still uncertain?
   ├── Verified mode → targeted AI review/repair
   └── Standard mode → preserve safest representation + warning metadata
```

### Confidence requirements

Every recognized equation must carry at least:

- recognizer confidence
- structural validation result
- render comparison result when available
- final acceptance status

Suggested initial policy:

```text
>= 0.95
  → accept after structural validation

0.80–0.949
  → lightweight secondary validation

0.60–0.799
  → fallback recognizer or stronger model

< 0.60
  → do not silently trust
  → escalate or preserve as image fallback
```

These thresholds are starting points only and must be calibrated against the golden corpus.

### Mathematical equivalence checks

Where possible, verify:

- parse validity
- balanced delimiters
- valid LaTeX/MathML syntax
- rendered visual similarity
- token/AST consistency
- equation-number association

For selected algebraic expressions, symbolic equivalence checks may be used as an additional signal, but symbolic simplification must never be the only correctness test.

### Product rule

A wrong editable equation is worse than a clearly marked non-editable fallback.

The system must prefer:

**correctness > editability > cosmetic perfection.**

---

## 60.2 OMML / Word equation complexity

### Risk

LaTeX and OMML are not identical representations. Microsoft documents both supported LaTeX-to-Office-Math mappings and limitations; for example, some LaTeX display/text sizing distinctions are normalized because OMML does not preserve them per element. Therefore a generic LaTeX → OMML converter cannot be assumed to preserve every construct exactly. [Microsoft Learn: LaTeX support in Microsoft 365]

### Required architecture

Do not make LaTeX the final internal representation.

Use an intermediate mathematical representation:

```text
Equation image / source
        ↓
Math recognition
        ↓
Normalized MathIR
        ↓
OMML renderer
        ↓
Word equation
```

`MathIR` should represent structural concepts such as:

- fraction
- root
- superscript
- subscript
- operator
- function
- matrix
- cases
- accent
- fence
- integral
- sum
- limit
- text/run
- aligned row
- equation numbering

### OMML renderer requirements

The OMML layer must be:

- deterministic
- versioned
- unit-tested
- independent from any specific OCR model
- capable of reporting unsupported constructs

### Unsupported construct handling

If a recognized mathematical construct cannot be safely represented:

1. Attempt a supported equivalent representation.
2. Validate the generated OMML by rendering.
3. If still unsafe, use the product's explicit math-image fallback.
4. Record the fallback in quality metadata.
5. Never claim 100% editability for a fallback image.

### Word round-trip test

A representative corpus must be tested through:

```text
MathIR
 ↓
OMML
 ↓
DOCX
 ↓
Word-compatible rendering
 ↓
Visual/structural comparison
```

Any OMML change must run this regression suite.

---

## 60.3 Processing cost and AI budget protection

### Risk

AI verification and repair can become the largest variable cost if every page is sent to an expensive model or if retries are unbounded.

### Required architecture

AI must be selective.

Do not do:

```text
Every page
  ↓
Strong AI model
```

Prefer:

```text
Every page
  ↓
Cheap deterministic checks
  ↓
Only suspicious regions
  ↓
AI verification
```

### Hard controls

Every job must have:

- maximum processing time
- maximum retry count
- maximum verification attempts
- maximum AI spend budget
- maximum pages
- maximum concurrent expensive tasks

Example:

```text
maxRepairAttempts = 2
maxVerificationPasses = 2
maxExpensiveRegionsPerJob = configurable
```

### User/account controls

Every plan must have:

- conversion page allowance
- verification allowance
- daily abuse ceiling
- concurrent-job limit
- file-size limit

### Cost-aware routing

The AI router should consider:

- current free allocation
- provider price
- model capability
- context length
- latency
- provider health
- job budget

The router must be able to stop rather than spend beyond the job's budget.

### Free allocation strategy

Where an inference provider supplies a free daily allowance, use it first where practical. Cloudflare Workers AI currently documents a 10,000-neuron/day free allocation, but the production system must not depend on that single provider or assume the free allowance is sufficient for every workload.

### Caching

Cache safe deterministic intermediates:

- page renders
- extracted figures
- normalized math representations
- repeated verification artifacts where content hashes match

Never cache private user content across users.

---

## 60.4 Commercial license compliance

### Risk

"Open source" does not automatically mean that every released model weight is commercially deployable.

Current examples:

- Marker code is Apache-2.0, but its current model weights have a separate modified OpenRAIL-M licensing arrangement with commercial-use conditions. [Official Marker README]
- Docling code is MIT, while individual model usage must be checked against the relevant model licenses. [Official Docling repository]
- pix2tex code is MIT, but its released pretrained weights are CC BY-NC-SA according to its weight release. [Official pix2tex release]
- Nougat code is MIT while its model weights are CC BY-NC, so the current weights are not a default production choice for this commercial SaaS. [Official Nougat repository]

### Required architecture

Create a `LICENSE_GATE` for every production model/dependency:

```text
Candidate
  ↓
Record exact repository
  ↓
Record exact commit/version
  ↓
Record code license
  ↓
Record model-weight license
  ↓
Record dataset/license obligations where material
  ↓
Review commercial SaaS compatibility
  ↓
Approve / reject
```

### Production rule

A dependency is not production-approved until its:

- code license
- weight license
- major dependency licenses
- usage restrictions

have been reviewed.

If a candidate is not clearly commercially usable, it can remain in the benchmark/research environment but must not be shipped in the paid production path.

### Long-term preferred position

Prefer:

1. permissively licensed commercial-safe code/models,
2. commercially licensed model weights,
3. company-owned/fine-tuned weights with verified training-data rights.

---

## 60.5 Scalability for large PDFs

### Risk

A 500+ page document cannot safely be treated as one giant in-memory processing object.

### Required architecture

Process documents page-by-page or in bounded chunks.

Preferred flow:

```text
Large PDF
   ↓
Metadata analysis
   ↓
Page manifest
   ↓
Chunk planner
   ↓
Chunk 1 (e.g. 5–20 pages)
Chunk 2 (e.g. 5–20 pages)
Chunk 3
...
   ↓
Independent processing
   ↓
Persist page/chunk artifacts
   ↓
Merge ordered DocumentModel
   ↓
DOCX reconstruction
```

The exact chunk size must be benchmarked based on:

- page complexity
- memory use
- model type
- GPU VRAM
- CPU memory
- latency
- retry cost

### Checkpointing

Every processed chunk must have a durable checkpoint.

If chunk 17 fails:

```text
Do not restart 1–16.
Retry 17 only.
```

### Bounded concurrency

Concurrency must be controlled by:

- available CPU
- available RAM
- GPU VRAM
- provider limits
- account/job quotas

Do not create unlimited parallel inference jobs for a single upload.

### Streaming and artifact discipline

Do not keep:

- full PDF bytes
- all rendered pages
- all image tensors
- all intermediate representations

in one process memory scope.

Use object storage and short-lived local working directories for intermediate artifacts.

### Final assembly

The final document assembly stage should consume the canonical `DocumentModel` and retrieve only the assets required for the current assembly operation.

### Large-file UX

For large documents:

- show stage-based progress
- show pages/chunks processed
- allow the user to leave the browser
- persist job state
- allow resume after transient failures

---

## 60.6 Job isolation and failure containment

One problematic page must not automatically destroy a 500-page job.

Each page/chunk should have:

- status
- attempt count
- error code
- processing duration
- model/provider used
- artifact references
- quality metadata

A job can complete with warnings when the overall product threshold is still met.

Example:

```text
495 pages successful
3 pages repaired
2 pages flagged for review
```

This should become:

`completed_with_warnings`

rather than a total failure, if the product's quality policy allows it.

---

## 60.7 No silent degradation

A conversion must record what happened.

For every page/region, track enough metadata to answer:

- Was it extracted or OCR'd?
- Which recognizer was used?
- Was a fallback used?
- Was the equation native OMML or image fallback?
- Was the region verified?
- Was an AI repair applied?

Users do not need to see all of this, but the system must retain it for QA and debugging.

---

# 61. Reliability and Quality Gates

Every production release affecting document processing must pass:

## Math gate

- Representative simple equations.
- Complex fractions.
- Matrices.
- Calculus.
- Multi-line equations.
- Equation numbering.
- Inline math.
- Symbols.

## OMML gate

- DOCX opens.
- Equations are editable.
- Word rendering succeeds.
- No malformed OOXML.

## Layout gate

- One-column.
- Two-column.
- Mixed figures.
- Captions.
- Tables.
- Page breaks.

## Large-document gate

- 100 pages.
- 250 pages.
- 500 pages.
- At least one stress test above the normal paid-plan maximum.

## Cost gate

- Maximum cost per job.
- Maximum AI calls.
- Maximum retries.
- Maximum GPU time.

## License gate

- Exact production versions recorded.
- Licenses reviewed.
- No unapproved model weights.

A release cannot be considered production-ready if any applicable gate fails.

---

# 62. Gold Corpus and Red-Team Corpus

Maintain two permanent datasets.

## Gold corpus

Representative normal customer-like documents, including:

- textbooks
- worksheets
- exams
- academic papers
- engineering documents
- physics documents
- multi-column papers
- equations embedded in tables
- equation-heavy pages

## Red-team corpus

Intentionally difficult cases:

- nested fractions
- unusual fonts
- matrices
- very long equations
- equations crossing line boundaries
- dense two-column layouts
- tables containing equations
- complex figures
- huge documents
- malformed PDFs
- PDFs with broken embedded text
- mixed native/scanned pages

Every engine/model change must be evaluated against both corpora.

---

# 63. Architecture Decision: Prototype vs Production Components

Use a two-lane component strategy.

## Lane A — Prototype / benchmark

May contain:

- pix2tex released weights
- Nougat weights
- experimental VLMs
- any other candidate useful for evaluation

These components can generate benchmark data only.

## Lane B — Commercial production

May contain only:

- commercially cleared models/weights
- permissively licensed components
- company-owned models
- paid/licensed components with verified terms

This separation allows experimentation without accidentally shipping a licensing problem.


# 64. Risk Acceptance Checklist

Before public launch, the following must be demonstrated in staging, not merely documented:

- [ ] Math recognition has at least two evaluated paths or a documented commercial-safe fallback.
- [ ] Low-confidence equations are never silently treated as correct.
- [ ] Image fallback is tracked in internal quality metadata.
- [ ] Representative matrices, piecewise functions, aligned equations and multi-line equations are in the regression corpus.
- [ ] The MathIR → OMML renderer has a Word round-trip test suite.
- [ ] Unsupported OMML constructs produce explicit fallback/warning behavior.
- [ ] Per-job AI/GPU budgets are enforced server-side.
- [ ] Verification retry count is bounded.
- [ ] Production model/dependency license approvals are recorded.
- [ ] A 500+ page stress test completes without unbounded memory growth.
- [ ] Large jobs resume from the failed chunk rather than restarting from page 1.
- [ ] Anonymous abuse controls have been load-tested.
- [ ] CAPTCHA/account escalation triggers correctly.
- [ ] Closing the browser does not cancel processing.
- [ ] Refresh restores the correct job state.
- [ ] SSE or polling fallback restores updates after reconnect.
- [ ] Session expiration does not terminate an already-authorized job.
- [ ] Result access still requires valid authorization.
- [ ] No UI invents percentage progress.
- [ ] Two-column reading-order benchmark passes the defined acceptance threshold.
- [ ] Expired files are actually deleted and deletion failures are retried/alerted.
- [ ] Dodo webhook duplicates and out-of-order events are handled safely.
- [ ] Subscription state can be reconciled against the payment provider.
- [ ] AI provider adapters can be swapped without changing business logic.
- [ ] Mobile upload/progress/result flows pass the real-device matrix.

A launch blocker is any critical-risk control marked failed or unverified.

---

# 65. Implementation Order

This is the recommended build sequence.

## Phase 1 — Repository foundation

Build:

- Next.js app.
- TypeScript.
- Design system.
- Routing.
- Environment management.
- Basic CI.

Definition of done:

- App runs locally.
- Preview deployment works.
- Public homepage renders.

## Phase 2 — Authentication + Supabase

Build:

- Supabase project.
- Auth.
- Profiles.
- RLS.
- Base schema.

Definition of done:

- User can sign up.
- User can sign in.
- Protected dashboard works.
- Unauthorized user cannot access another user's data.

## Phase 3 — File storage + upload

Build:

- R2 bucket.
- Secure upload flow.
- File metadata.
- Validation.

Definition of done:

- User uploads PDF.
- PDF is stored securely.
- User sees uploaded job.

## Phase 4 — Job system

Build:

- Conversion job table.
- Queue/workflow.
- Status updates.
- Retries.
- Idempotency.

Definition of done:

- Upload creates a job.
- Job progresses asynchronously.
- Failure is recoverable.

## Phase 5 — DocumentModel

Build:

- Canonical schemas.
- Validators.
- Serialization.
- Versioning.

Definition of done:

- Sample parsed document can be represented losslessly enough for the current target feature set.

## Phase 6 — PDF analysis

Integrate/benchmark candidate parsers.

Start with Marker/Docling benchmark.

Definition of done:

- Born-digital PDFs can be parsed.
- Text blocks and geometry are available.
- Figures/tables/equations can be identified for test fixtures.

## Phase 7 — Math engine

Integrate candidate math recognizer(s) behind the `MathRecognizer` interface.

Do not lock production to stock pix2tex weights until the license gate passes. Use the benchmark corpus to select the commercially approved recognizer.

Definition of done:

- Representative equation corpus produces normalized math representations.
- Confidence is recorded.

## Phase 8 — DOCX engine

Build:

- Paragraphs.
- Headings.
- Images.
- Tables.
- Native OMML equations.

Definition of done:

- DOCX opens in Word.
- Equation editing works for supported test cases.

## Phase 9 — Fidelity engine

Build:

- Layout mapping.
- Columns.
- Captions.
- Equation numbering.
- Header/footer support.

Definition of done:

- Core benchmark documents have acceptable visual/semantic fidelity.

## Phase 10 — Verification

Build:

- DOCX render/check.
- Source/output comparison.
- Suspicious region detection.
- AI router.
- Targeted repair.

Definition of done:

- Verified mode can catch known seeded errors.

## Phase 11 — Billing + usage

Build:

- Plans.
- Entitlements.
- Usage accounting.
- Dodo checkout.
- Webhooks.
- Credit system.

Definition of done:

- Full/empty quota behavior works.
- Successful payment changes access.
- Failed payment doesn't grant incorrect entitlement.

## Phase 12 — Dashboard/history

Build:

- Dashboard.
- History.
- Job detail.
- Usage.
- Billing.
- Settings.

## Phase 13 — SEO/legal

Build:

- Pricing.
- FAQ.
- Privacy.
- Terms.
- Security.
- Refunds.
- SEO landing pages.
- Blog.

## Phase 14 — Hardening

Build:

- Rate limits.
- Monitoring.
- Alerting.
- Cost controls.
- Abuse protection.
- Backup/recovery.
- License audit.
- Production benchmark.

---

# 66. Local Development Workflow

Recommended loop:

```text
Implement one module
 ↓
Run unit tests
 ↓
Run sample PDF
 ↓
Inspect DocumentModel
 ↓
Generate DOCX
 ↓
Open/render DOCX
 ↓
Compare against source
 ↓
Add regression test
```

Do not build the entire pipeline and only test at the end.

---

# 67. AI Coding-Agent Workflow

Any AI coding agent working on this repository must:

1. Read `docs/architecture.md` first.
2. Identify the module being changed.
3. Check the contract/interface before modifying adjacent systems.
4. Prefer existing approved dependencies before introducing new ones.
5. Check license requirements for new open-source dependencies.
6. Run relevant tests.
7. Update tests for changed behavior.
8. Avoid unrelated refactors.
9. Update this architecture when a major architectural decision changes.

The agent must not replace a core subsystem solely because another library is easier to install.

---

# 68. Design/Frontend Workflow for AI Agents

When generating UI:

- Read the PRD.
- Read this architecture.
- Use the approved design skills.
- Avoid generic AI-dashboard aesthetics.
- Keep the upload/conversion flow visually obvious.
- Prefer useful hierarchy over decorative motion.
- Keep accessibility and responsive behavior in scope.

Primary visual priorities:

1. Trust.
2. Clarity.
3. Conversion action.
4. Result quality.
5. Usage/billing transparency.

---

# 69. File/Artifact Naming

Use stable IDs and descriptive names.

Example storage:

```text
users/{userId}/jobs/{jobId}/source.pdf
users/{userId}/jobs/{jobId}/output.docx
users/{userId}/jobs/{jobId}/assets/{assetId}.png
users/{userId}/jobs/{jobId}/verification/{artifact}.pdf
```

Do not allow user-provided filenames to determine the actual storage key.

---

# 70. Data Ownership Boundaries

## Supabase

Owns:

- User identity references.
- App records.
- Jobs.
- Usage.
- Entitlements.
- Feedback.

## R2

Owns:

- File bytes.

## Dodo

Owns:

- Payment processing and billing events.

## Resend

Owns:

- Email delivery.

## AI providers

Only receive the minimum content required by the approved processing path.

---

# 71. Operational Alerts

Alert on:

- queue backlog above threshold.
- conversion failure rate above threshold.
- provider outage.
- AI provider cost anomaly.
- GPU cost spike.
- webhook failures.
- email failure spikes.
- storage errors.
- unexpected quota/entitlement mismatch.

---

# 72. Backup and Recovery

Back up:

- database.
- configuration.
- important metadata.

User-uploaded files may be governed by retention rather than indefinite backup depending on the product policy.

Recovery goals must be defined before production launch.

---


## 72.1 Disaster recovery objectives

### Recovery Time Objective (RTO)

- Core web application: **≤ 4 hours**.
- Conversion processing: **≤ 4 hours** to resume normal queue intake after a regional/provider outage when fallback infrastructure is available.
- Admin/analytics: **≤ 24 hours**.

### Recovery Point Objective (RPO)

- Application metadata, billing and job state: **≤ 15 minutes**.
- User file artifacts: governed by retention policy; Business/enterprise tiers may use stronger replicated-artifact guarantees.
- Ephemeral processing artifacts: may be regenerated from the source PDF when the source is still within retention.

### Database backups

Minimum production policy:

- Continuous/PITR capability where supported by the database tier.
- Daily full backup/snapshot.
- 30-day backup retention for production metadata.
- Monthly restore-drill test for the latest backup.

The exact backup mechanism may use Supabase-native backup/PITR features or an equivalent managed PostgreSQL backup solution, but the RPO/RTO targets remain mandatory.

### Object storage

For retained user files:

- Versioning where supported.
- Encrypted storage.
- Lifecycle expiration aligned with privacy policy.
- Optional cross-region replication for Business/enterprise workloads when a stronger RPO is sold.

Do not silently create long-lived backups that contradict the user-facing retention policy.

### Failover strategy

```text
Primary web/API layer
        ↓ unavailable
Edge continues serving static/public pages where possible
        ↓
Application traffic fails over or enters degraded mode
        ↓
Job queue pauses unsafe writes if DB is unavailable
        ↓
GPU/provider processing can fail over independently
        ↓
After recovery, reconciliation resumes unfinished jobs safely
```

### Billing disaster recovery

Payment provider webhooks are not the only source of truth for recovery. Periodic reconciliation against Dodo must detect:

- missing webhook events
- subscription state drift
- duplicate events
- payment/refund mismatches

### Restore test requirement

A production launch is blocked until the team successfully demonstrates:

1. database restore;
2. application configuration restore;
3. job-state recovery;
4. billing reconciliation;
5. reprocessing of an interrupted conversion;
6. correct user access after restore.

# 73. Future Expansion Points

The architecture should allow future additions without replacing the core model.

Potential future outputs:

- LaTeX.
- Markdown.
- HTML.
- EPUB.

Potential future inputs:

- Scanned PDFs.
- Images.
- DOCX.
- EPUB.

Potential product features:

- Review editor.
- Batch conversion.
- API.
- Team workspaces.
- Enterprise/private processing.
- Question-bank extraction.
- Study-note generation.

---

# 74. API Future Architecture

Future public API:

```text
POST /v1/conversions
GET  /v1/conversions/{id}
GET  /v1/conversions/{id}/download
POST /v1/credits
```

The internal job system should already use a similar contract so the public API can later be added without rebuilding the processing pipeline.

---

# 75. Enterprise Architecture Future

For enterprise:

- Organization accounts.
- SSO.
- Team permissions.
- Shared quota.
- Audit logs.
- Dedicated processing.
- Data residency options where feasible.
- No-training/no-retention configurations where supported.
- Contractual data-processing controls.

Do not build all of this in MVP, but keep the boundaries clean enough to add it later.

---

# 76. Critical Architectural Decisions

The following are intentional decisions:

### Keep

- Next.js.
- React.
- TypeScript.
- Cloudflare.
- Supabase.
- Dodo Payments.
- Resend.
- R2.
- Existing design/engineering skills.

### Remove for MVP

- Turso as a second app database.
- RAG as the core architecture.
- Permanent always-on GPU.
- Vendor lock-in to one AI model.

### Add

- DocumentModel.
- PDF/document pipeline.
- Math engine.
- OMML/DOCX engine.
- Table engine.
- Figure engine.
- Verification engine.
- AI router.
- Queue/job system.
- Usage/quota engine.
- License audit.
- Benchmark corpus.
- Admin/operations.

---

# 77. Architecture Non-Goals

This architecture does not promise:

- Perfect conversion of every PDF.
- Perfect handwriting recognition.
- Unlimited compute.
- Unlimited lifetime processing.
- One specific AI provider forever.
- A single open-source parser as the permanent foundation.

The system is designed to improve by replacing individual pipeline components.

---

# 78. Definition of Production Readiness

The product is ready for production when all of the following are true:

## Application

- Public website works.
- Auth works.
- Tool works.
- Dashboard works.
- History works.
- Billing works.
- Legal pages exist.
- Account deletion works.

## Conversion

- Target born-digital PDFs process reliably.
- Text is preserved.
- Equations become native Word equations for supported cases.
- Figures are preserved.
- Tables are reconstructed.
- Reading order is acceptable.

## Verification

- Verified mode catches seeded errors.
- AI routing has hard cost limits.
- Repair loop is bounded.

## Security

- RLS validated.
- Secrets protected.
- Storage access protected.
- Webhooks verified.

## Operations

- Logs available.
- Errors categorized.
- Queue monitored.
- Costs measurable.
- Backups/recovery plan defined.

## Legal

- Open-source license audit complete.
- AI provider terms reviewed.
- Privacy policy matches real data flows.
- Terms/refund policy published.

---

# 79. First Engineering Task List

After creating the repository, work in this order:

```text
[ ] Create monorepo/app structure
[ ] Create Next.js app
[ ] Create design system
[ ] Add Supabase
[ ] Add auth
[ ] Add RLS
[ ] Create base database schema
[ ] Add R2
[ ] Build upload flow
[ ] Create conversion_jobs
[ ] Add queue/workflow
[ ] Create processor skeleton
[ ] Define DocumentModel v1
[ ] Benchmark Marker
[ ] Benchmark Docling
[ ] Benchmark math OCR candidates
[ ] Perform license audit
[ ] Select initial parser path
[ ] Build math-engine adapter
[ ] Build DOCX-engine skeleton
[ ] Implement OMML math
[ ] Implement images/figures
[ ] Implement tables
[ ] Implement layout
[ ] Build first end-to-end conversion
[ ] Build regression corpus
[ ] Build verification prototype
[ ] Add AI router
[ ] Add usage engine
[ ] Add Dodo
[ ] Add Resend
[ ] Build dashboard/history
[ ] Build pricing page
[ ] Build legal pages
[ ] Build admin tools
[ ] Run production benchmark
[ ] Run security review
[ ] Launch private beta
```

---

# 80. Engineering Rules That Must Not Be Violated

1. Do not put heavy PDF/ML work in the normal request-response path.
2. Do not expose service secrets in the browser.
3. Do not bypass Supabase RLS for ordinary user access.
4. Do not grant paid entitlements based on client-side state.
5. Do not trust payment webhooks without verification/idempotency.
6. Do not silently replace editable equations with images without tracking it.
7. Do not send whole documents to expensive AI models when a targeted region is sufficient.
8. Do not allow unbounded AI/GPU retries.
9. Do not add a second database without a measured reason.
10. Do not deploy an open-source model/weight before license review.
11. Do not change document engines without regression testing.
12. Do not let provider-specific code leak throughout the application.
13. Do not log raw confidential document content by default.
14. Do not promise “100% identical” unless benchmarked and proven.
15. Prefer the simplest architecture that satisfies the current product requirements.

---

# 81. Final Architecture Summary

The product is a full-stack SaaS with a lightweight web/application layer and a specialized asynchronous document-processing engine.

The core data flow is:

```text
User
 ↓
Next.js / React
 ↓
Cloudflare Edge/API
 ↓
Supabase Auth + App DB
 ↓
R2 File Storage
 ↓
Conversion Job
 ↓
PDF Analysis
 ↓
Document Understanding
 ↓
Math/Text/Table/Figure Recognition
 ↓
Canonical DocumentModel
 ↓
DOCX Reconstruction
 ↓
Native Word Equation Generation
 ↓
Verification
 ↓
AI Provider Router when needed
 ↓
Repair/re-check
 ↓
Final DOCX
 ↓
R2
 ↓
Authorized Download
 ↓
History + Usage + Notifications
```

The product layer around that engine is:

```text
Marketing Website
+ Conversion Tool
+ Authentication
+ Dashboard
+ History
+ Usage
+ Billing
+ Settings
+ Legal/Privacy
+ SEO Content
+ Admin/Operations
```

The architecture is intentionally modular so that the product can start with open-source building blocks and replace individual parsers, math models, inference providers, or GPU backends as quality, cost, licensing, or scale requirements change.

The final objective is not merely to create a `.docx` file.

The objective is:

> **Create a Word document that a teacher, student, researcher, engineer, publisher or content creator can actually continue editing — especially the mathematics — without rebuilding the document manually.**

## 81.1 Architecture Review Status — v1.3 / v5 package

The following previously identified minor gaps are now explicitly resolved:

- [x] Duplicate disaster-recovery subsection numbering corrected to `72.1`.
- [x] MathIR schema is provided as an executable companion artifact and has a repository path, validation gate, fixtures and versioning rules.
- [x] Monitoring stack explicitly defined: Sentry + OpenTelemetry + Cloudflare + Supabase diagnostics.
- [x] CI/CD structure explicitly defined with PR, preview, staging and production stages.
- [x] Data migration strategy explicitly defined using versioned migrations and expand/contract releases.
- [x] Testing pyramid ratios and coverage targets defined.
- [x] Authentication mechanism explicitly defined: Supabase cookie sessions for web, controlled service credentials for internal APIs.
- [x] File upload sizes explicitly defined by plan.
- [x] Retention periods explicitly defined by plan and artifact type.
- [x] Queue implementation explicitly selected: Cloudflare Queues with DLQ and pull consumer integration for external processors.

This document remains a blueprint. Actual production readiness still requires the acceptance checklist, benchmark results, license approvals, and live restore/cost/quality validation described above.
