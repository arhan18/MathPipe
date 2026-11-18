# User Flow & Interaction Specification

## Product

Math-first PDF → Editable Word SaaS

This document describes how a user moves through the product, what happens after each click, which page or state appears next, and how the major application flows connect.

It is a product-flow document, not a backend architecture document. It should be used alongside `PRD.md` and `architecture.md`.

---

# 1. Global Product Structure

The application has five major surfaces:

1. Public marketing website
2. PDF conversion tool
3. Authenticated user dashboard
4. Billing/account area
5. Internal/admin area

High-level flow:

```text
Visitor
  │
  ├── Learn about product
  │      │
  │      ├── Pricing
  │      ├── Features
  │      ├── FAQ
  │      ├── Blog / Guides
  │      └── SEO landing pages
  │
  └── Start converting
         │
         ▼
      Upload / Convert
         │
         ├── Anonymous / Free flow
         │
         └── Login / Signup when required
                    │
                    ▼
                Dashboard
                    │
          ┌─────────┼──────────┐
          ▼         ▼          ▼
      Convert    History     Usage
          │                     │
          ▼                     ▼
       Result                Billing
          │
          ▼
      Download DOCX
```

---

# 2. Route Map

## Public routes

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

 /privacy
 /terms
 /cookie-policy
 /security
 /refund-policy
```

## Authentication routes

```text
/login
/signup
/forgot-password
/reset-password
```

## Application routes

```text
/convert
/dashboard
/dashboard/history
/dashboard/history/[conversionId]
/dashboard/files
/dashboard/usage
/dashboard/billing
/dashboard/settings
/dashboard/settings/profile
/dashboard/settings/security
/dashboard/settings/privacy
```

## Admin routes

```text
/admin
/admin/users
/admin/jobs
/admin/conversions
/admin/usage
/admin/billing
/admin/feedback
/admin/system
```

---

# 3. Primary User Journey

The main journey should be as simple as possible:

```text
Landing page
   ↓
Click "Convert a PDF Free"
   ↓
Conversion page
   ↓
Upload PDF
   ↓
PDF validation
   ↓
Choose conversion mode
   ↓
Start conversion
   ↓
Processing screen
   ↓
Verification if enabled
   ↓
Conversion result
   ↓
Download DOCX
   ↓
Optional signup / account creation
   ↓
Dashboard + conversion history
```

The core product should minimize the number of screens between upload and successful download.

---

# 4. Landing Page Flow

## Page

`/`

## Main actions

Primary CTA:

**Convert a PDF Free**

Secondary CTAs:

- See how it works
- Pricing
- Features
- Sign in

---

## 4.1 User clicks "Convert a PDF Free"

Destination:

```text
/convert
```

The user should immediately see the upload interface.

If anonymous free conversion is allowed, do not force signup before upload.

If the product requires an account for conversion, show:

```text
/signup?next=/convert
```

After successful signup, redirect the user back to:

```text
/convert
```

---

# 5. Navigation From Homepage

## Click "Features"

Go to:

```text
/features
```

## Click "Pricing"

Go to:

```text
/pricing
```

## Click "How It Works"

Go to:

```text
/how-it-works
```

## Click "FAQ"

Go to:

```text
/faq
```

## Click "Sign In"

Go to:

```text
/login
```

## Click "Get Started"

Go to:

```text
/convert
```

## Click logo

Go to:

```text
/
```

---

# 6. Pricing Flow

## Page

`/pricing`

Display:

- Free
- Pro
- Power
- Heavy / Business where applicable

Each plan should show:

- Monthly price
- Conversion page allowance
- Verified page allowance
- File-size limit
- Batch availability
- Priority processing
- Team features where applicable

---

## 6.1 User clicks "Upgrade"

If not logged in:

```text
/pricing
   ↓
Click Upgrade
   ↓
/login?next=/pricing
   ↓
Authenticate
   ↓
Return to selected plan checkout
```

If already logged in:

```text
/pricing
   ↓
Click Upgrade
   ↓
Dodo checkout
```

After successful payment:

```text
Dodo checkout
   ↓
Payment success
   ↓
Billing webhook
   ↓
Subscription state updated
   ↓
Return to application
   ↓
/checkout/success or /dashboard
```

The dashboard should show the new plan immediately after the application receives the confirmed billing state.

---

# 7. Sign Up Flow

## Page

`/signup`

Methods:

- Google
- Microsoft where enabled
- Email
- Password / magic link depending on final authentication implementation

---

## 7.1 Successful signup

After signup:

```text
Signup
  ↓
Create user
  ↓
Create user profile
  ↓
Create free plan state
  ↓
Initialize usage counters
  ↓
Optional welcome email
  ↓
Return to intended destination
```

Examples:

If user came from:

```text
/signup?next=/convert
```

redirect to:

```text
/convert
```

If user came from the normal signup button:

```text
/signup
```

redirect to:

```text
/dashboard
```

---

# 8. Login Flow

## Page

`/login`

After successful login:

### If there is an intended destination

Return to that destination.

### Otherwise

Go to:

```text
/dashboard
```

---

# 9. Main Conversion Tool Flow

## Page

`/convert`

This is the core product page.

The first state should contain:

```text
Upload your PDF

Drag and drop
or
Choose file

Supported: PDF

[Choose PDF]
```

Also show:

- current plan
- pages remaining
- verification allowance
- relevant file-size limit

---

# 10. Upload Interaction

## User clicks "Choose PDF"

Open native file picker.

User selects a PDF.

Then:

```text
File selected
   ↓
Upload begins
```

Show:

```text
filename.pdf
12.4 MB
Uploading...
████████░░
```

---

# 11. File Validation Flow

After upload:

```text
Upload
 ↓
Validate PDF
 ↓
Check:
 - file type
 - file size
 - page count
 - corruption
 - supported structure
```

## Valid PDF

Proceed to:

```text
Conversion settings
```

## Invalid PDF

Remain on `/convert` and show an actionable error.

Examples:

```text
This file is too large for your current plan.
[Upgrade]
```

or:

```text
We couldn't read this PDF.
Please export it again and try again.
```

Do not send the user to a generic error page unless the entire application is unavailable.

---

# 12. Conversion Settings

After a valid upload, show the user a simple settings panel.

Possible choices:

### Conversion mode

- Standard
- Verified

### Pages

- Entire document
- Selected pages

Example:

```text
Pages:
[1-12]
```

The interface should show the estimated usage before starting.

Example:

```text
12 pages
Standard conversion
Uses 12 conversion pages
```

For Verified:

```text
12 pages
Verified conversion
Uses 12 conversion pages + verification allowance
```

---

# 13. User Clicks "Convert"

When the user clicks:

**Convert**

the interface should immediately create a conversion job.

Flow:

```text
Click Convert
   ↓
Check authentication
   ↓
Check plan/usage
   ↓
Create conversion job
   ↓
Show processing screen
```

If the user does not have enough credits/pages:

```text
Usage exceeded
   ↓
Show upgrade modal
```

Example:

> You have used all 10 free pages this month.

Actions:

**Upgrade**

**View Plans**

**Cancel**

---

# 14. Processing Screen

Route:

```text
/convert?job=<id>
```

or a dedicated job route:

```text
/dashboard/conversions/<id>
```

The UI should show live status.

Example:

```text
Converting your PDF

✓ Upload complete
✓ PDF analyzed
✓ Text detected
✓ Mathematics detected
● Reconstructing Word document
○ Verifying document
○ Finalizing DOCX
```

The exact progress should be truthful.

Do not show fake percentage progress if the backend cannot estimate it.

---

# 15. Conversion Job States

The frontend should handle these states:

```text
queued
uploading
analyzing
processing
reconstructing
verifying
repairing
finalizing
completed
completed_with_warnings
failed
cancelled
expired
```

Each state has a corresponding UI.

---

# 16. Standard Conversion Flow

For Standard mode:

```text
PDF
 ↓
Analyze
 ↓
Extract text
 ↓
Detect math
 ↓
Detect tables
 ↓
Detect figures
 ↓
Build structured document
 ↓
Create DOCX
 ↓
Final validation
 ↓
Completed
```

User sees:

```text
Your Word file is ready.
```

Primary button:

**Download DOCX**

Secondary:

**View Details**

---

# 17. Verified Conversion Flow

For Verified mode:

```text
PDF
 ↓
Analyze
 ↓
Convert
 ↓
Create initial DOCX
 ↓
Render/check output
 ↓
Compare with source
 ↓
Find suspicious regions
 ↓
AI verification
 ↓
Repair where safe
 ↓
Re-check
 ↓
Finalize DOCX
```

User sees messages such as:

```text
Conversion complete

Verified 34 pages
Checked 116 equations
Found 2 low-confidence regions
Automatically repaired 1
```

If everything passes:

```text
Verified successfully
```

---

# 18. Completed Result State

The completion page should show:

```text
Your Word document is ready

filename.docx

34 pages
116 equations
7 tables
19 figures

Conversion: Complete
Verification: Complete
```

Primary CTA:

**Download DOCX**

Secondary CTAs:

- Convert another PDF
- View history
- Report a problem

---

# 19. Download Flow

User clicks:

**Download DOCX**

The browser downloads the generated `.docx`.

The conversion remains saved in history.

After download, optionally show:

> How was your conversion?

👍 Great

👎 Needs improvement

This feedback should be optional and not block the workflow.

---

# 20. "Convert Another PDF"

User clicks:

**Convert another**

Destination:

```text
/convert
```

The upload area resets to its initial state.

Current usage counters remain visible.

---

# 21. "View History"

User clicks:

**View history**

Destination:

```text
/dashboard/history
```

The most recent conversion should appear at the top.

---

# 22. Dashboard Flow

## Page

`/dashboard`

Dashboard should contain:

### Greeting

Example:

> Welcome back.

### Quick action

**Convert a PDF**

### Usage

```text
324 / 500 conversion pages
32 / 50 verified pages
```

### Recent conversions

List the latest files.

### Current plan

Show plan and renewal information.

---

# 23. Dashboard Quick Upload

User clicks:

**Convert a PDF**

Destination:

```text
/convert
```

This should be the most prominent dashboard action.

---

# 24. History Flow

## Page

`/dashboard/history`

Show:

- filename
- date
- page count
- mode
- status
- verification state
- download

Each row is clickable.

---

# 25. User Clicks a History Item

Destination:

```text
/dashboard/history/[conversionId]
```

Show:

- file name
- date/time
- original page count
- conversion mode
- status
- verification results
- download
- retry if supported
- delete
- report issue

---

# 26. Retry Flow

If a conversion failed:

User clicks:

**Retry**

Flow:

```text
History detail
 ↓
Retry
 ↓
Check remaining usage
 ↓
Create new processing attempt
 ↓
Processing screen
```

The old failed attempt remains visible in the audit/history system if appropriate.

---

# 27. Delete Conversion

User clicks:

**Delete**

Show confirmation:

> Delete this conversion and its generated files?

Actions:

**Delete**

**Cancel**

After deletion:

```text
/dashboard/history
```

The record should disappear from the normal user view.

---

# 28. Files Page

## Page

`/dashboard/files`

Shows user files and generated outputs when this feature is enabled.

Possible columns:

- File name
- Type
- Size
- Created
- Expires
- Status
- Actions

Actions:

- Download
- Delete

---

# 29. Usage Page

## Page

`/dashboard/usage`

Display:

```text
Current plan
500 conversion pages
1,500 pages total
```

and:

```text
Verified:
32 / 50
```

Also show:

- reset date
- extra credits
- recent usage
- usage history

---

# 30. Upgrade From Usage Page

If user reaches the limit:

```text
Usage page
 ↓
Upgrade
 ↓
Pricing/checkout
 ↓
Successful payment
 ↓
Return to usage/dashboard
 ↓
New limits displayed
```

---

# 31. Billing Page

## Page

`/dashboard/billing`

Display:

- current plan
- price
- next renewal
- payment status
- invoices
- upgrade/downgrade
- cancellation

---

# 32. Billing Upgrade Flow

User clicks:

**Upgrade**

Then:

```text
Select plan
 ↓
Dodo checkout
 ↓
Payment
 ↓
Webhook
 ↓
Account subscription updated
 ↓
Dashboard refreshed
```

Do not grant premium entitlements based solely on a client-side success screen. The backend subscription state should be authoritative.

---

# 33. Billing Cancellation Flow

User clicks:

**Cancel subscription**

Show confirmation.

After confirmation:

```text
Cancellation request
 ↓
Dodo subscription state updated
 ↓
Account retains current benefits until applicable end date
 ↓
Dashboard shows cancellation/renewal state
```

Exact behavior depends on final Dodo subscription configuration.

---

# 34. Settings Flow

## Page

`/dashboard/settings`

Sections:

```text
Profile
Security
Notifications
Privacy
Account deletion
```

---

# 35. Profile Flow

User can update:

- display name
- profile information
- email where supported

Click:

**Save changes**

Show:

> Changes saved.

---

# 36. Security Flow

Potential actions:

- change password
- view active sessions
- sign out all other sessions
- connected providers

Sensitive actions should require appropriate re-authentication.

---

# 37. Privacy Settings

Users should be able to understand:

- how long files are kept
- whether files are used for model improvement
- how AI providers may process content
- how to delete stored data

Where supported, provide:

**Delete my data**

---

# 38. Account Deletion Flow

User clicks:

**Delete account**

Show strong confirmation.

Possible flow:

```text
Delete account
 ↓
Re-authenticate if necessary
 ↓
Explain what will be deleted
 ↓
Confirm
 ↓
Delete account/data according to policy
 ↓
Sign out
 ↓
/
```

---

# 39. Legal Page Flow

Legal pages are publicly accessible.

Examples:

```text
/privacy
/terms
/cookie-policy
/security
/refund-policy
```

Footer links should expose these pages.

The user should not need to log in.

---

# 40. Blog / SEO Flow

User enters from Google:

```text
Google
 ↓
SEO page
 ↓
Read content
 ↓
CTA: Convert a PDF
 ↓
/convert
```

The conversion CTA should preserve campaign/referral context where analytics are enabled.

---

# 41. Programmatic SEO Page Flow

Example:

```text
/math-pdf-to-word
```

Page explains the use case.

Primary CTA:

**Convert Math PDF**

Click:

```text
/math-pdf-to-word
 ↓
/convert
```

The conversion page should remain generic enough to handle the uploaded document.

---

# 42. Comparison Page Flow

Example:

```text
/compare/mathpix-alternative
```

User reads comparison.

CTA:

**Try the Converter**

Destination:

```text
/convert
```

Avoid misleading or unverifiable competitor claims.

---

# 43. Anonymous User Flow

If anonymous conversion is supported:

```text
Visitor
 ↓
/convert
 ↓
Upload
 ↓
Free validation
 ↓
Conversion
 ↓
Download
 ↓
Prompt for account creation
```

The account prompt can say:

> Create a free account to keep your conversion history and continue converting PDFs.

Do not force signup earlier than necessary unless abuse data requires it.

---

# 44. Free User Flow

```text
Free user
 ↓
10 pages/month
 ↓
Convert
 ↓
Usage deducted
 ↓
Continue using product
```

When the limit is reached:

```text
Upload
 ↓
Usage check
 ↓
Limit reached
 ↓
Upgrade modal
 ↓
Pricing
```

---

# 45. Paid User Flow

```text
Paid user
 ↓
Upload
 ↓
Usage check
 ↓
Choose Standard or Verified
 ↓
Process
 ↓
Download
 ↓
Usage recorded
```

Paid users should receive premium processing options according to their plan.

---

# 46. Out-of-Quota Flow

When there are insufficient conversion credits:

```text
User clicks Convert
 ↓
Quota check
 ↓
Insufficient usage
 ↓
Modal
```

Example:

> You need 27 more pages for this document.

Buttons:

**Upgrade Plan**

**Buy Credits** (when available)

**Cancel**

No processing should start until the usage check passes.

---

# 47. Verification Limit Reached

If the user has enough conversion pages but not enough verification credits:

```text
Choose Verified
 ↓
Verification quota check
 ↓
Insufficient verification credits
```

Options:

**Convert without verification**

**Upgrade**

**Buy verification credits** where supported

This allows the conversion itself to remain useful even if the premium verification allowance is exhausted.

---

# 48. Large File Flow

User uploads a file above the plan limit.

Show:

```text
This file is larger than your current plan allows.
```

Options:

**Upgrade**

**Choose another file**

No processing job is created.

---

# 49. Unsupported Document Flow

If the file is technically a PDF but unsupported:

```text
Upload
 ↓
Analysis
 ↓
Unsupported structure detected
```

Show:

> This PDF type is not currently supported.

Possible CTA:

**Try another PDF**

If there is a future fallback mode:

**Try scanned-document mode**

---

# 50. Conversion Failure Flow

If the processing engine fails:

```text
Processing
 ↓
Failure
```

Show:

> We couldn't complete this conversion.

Buttons:

**Retry**

**Upload another PDF**

**Report problem**

If the failure was caused by infrastructure rather than usage, do not incorrectly blame the user.

---

# 51. Completed With Warnings

If output is usable but some regions are uncertain:

```text
Conversion complete
with warnings
```

Show:

- number of suspicious regions
- pages affected
- whether the user should review them

Primary:

**Download DOCX**

Secondary:

**Review Issues**

---

# 52. Review Issues Flow

When manual review is implemented:

```text
Result
 ↓
Review Issues
 ↓
Issue list
```

Example:

```text
Page 8
Equation 4
Low confidence
```

Click issue:

```text
Issue detail
```

Display:

```text
Original PDF crop
        vs
Converted result
```

Actions:

**Fix automatically**

**Edit**

**Ignore**

---

# 53. Automatic Repair Flow

User clicks:

**Fix automatically**

Then:

```text
Issue
 ↓
Repair job
 ↓
AI/model processing
 ↓
Rebuild region
 ↓
Re-render
 ↓
Re-verify
```

If successful:

> Fixed and verified.

If unsuccessful:

> We couldn't confidently fix this region.

No silent destructive modification.

---

# 54. Notifications

Transactional notifications may include:

### Email

- welcome
- conversion complete for long-running jobs
- conversion failure
- subscription confirmation
- payment failure
- renewal reminder where appropriate
- credit/usage warning

### In-app

- conversion status
- quota warning
- upgrade messages
- system announcements

Resend is the transactional email service in the current planned stack.

---

# 55. Usage Warning Flow

At configurable thresholds:

```text
80% used
90% used
100% used
```

Show an in-app warning.

Example:

> You have 48 conversion pages remaining this month.

At 100%:

> You've reached your monthly conversion limit.

CTA:

**Upgrade**

---

# 56. Admin Flow

Admin opens:

```text
/admin
```

Dashboard shows:

- active users
- jobs today
- failed jobs
- processing latency
- conversion success rate
- revenue
- AI/GPU spend
- system health

---

# 57. Admin Conversion Inspection

Admin clicks a failed conversion.

Open:

```text
/admin/conversions/[id]
```

Show:

- user
- file metadata
- job state
- processing stages
- failure reason
- provider used
- verification result
- duration
- resource usage
- retry controls

Do not expose file contents to admins unnecessarily; access should be controlled and audited.

---

# 58. Admin Feedback Flow

User reports:

> Equation 7 is wrong.

Admin can see:

- conversion ID
- page
- category
- user comment
- issue state

Possible states:

```text
new
investigating
fixed
wont_fix
duplicate
```

---

# 59. Global Navigation Behavior

## Desktop

Main public navigation:

```text
Logo
Features
How it Works
Pricing
Resources
[Sign In]
[Convert Free]
```

Authenticated navigation:

```text
Logo
Convert
Dashboard
History
Usage
Billing
Profile
```

## Mobile

Collapse into a mobile menu.

Primary CTA should remain easy to reach:

**Convert**

---

# 60. Breadcrumbs

Use breadcrumbs where depth becomes meaningful.

Example:

```text
Dashboard
  > History
    > Calculus-Chapter-3.pdf
```

Do not use unnecessary breadcrumbs on simple screens such as the homepage.

---

# 61. Back Navigation

The application should preserve context where practical.

Examples:

```text
History
 ↓
Conversion detail
 ↓
Back
```

returns to the user's history position.

Similarly:

```text
Pricing
 ↓
Checkout
 ↓
Success
```

should return users to a useful application state.

---

# 62. Browser Refresh Behavior

Refreshing during a conversion should not lose the job.

The conversion state is stored server-side.

After refresh:

```text
Job ID
 ↓
Fetch current state
 ↓
Render appropriate processing screen
```

---

# 63. Closing the Browser During Conversion

The job should continue independently of the browser where the underlying processing system supports this.

User can return later to:

```text
/dashboard/history
```

and see the job status.

---

# 64. Session Expiration During Conversion

If the user session expires while a job is running:

- processing should continue if already authorized
- the user should be required to re-authenticate for protected result access
- the job should not be silently abandoned

---

# 65. File Expiration Flow

When files reach the configured retention limit:

```text
Expiration time reached
 ↓
Delete temporary/source/result files
 ↓
Keep only minimal metadata if required by policy
```

History should clearly show when a result is no longer available.

Example:

> File expired.

Possible action:

**Convert again**

---

# 66. Referral / SEO Attribution

When arriving through a marketing or SEO page:

```text
Landing page
 ↓
Convert
```

preserve attribution information as appropriate for analytics.

Do not pass unnecessary personal data through URLs.

---

# 67. Loading and Empty States

Every major page needs an intentional empty state.

Examples:

### No history

> You haven't converted anything yet.

CTA:

**Convert your first PDF**

### No files

> Your generated documents will appear here.

### No billing history

> No invoices yet.

Avoid blank pages.

---

# 68. Responsive Behavior

The application should prioritize desktop for the actual document-processing workflow but remain functional on tablets and phones.

Desktop:

- two-column layouts where useful
- detailed progress
- file information
- usage panel

Mobile:

- stacked cards
- full-width upload
- simplified progress
- bottom or top navigation where appropriate

---

# 69. Core Click-to-Page Map

```text
HOME
│
├── Convert Free ───────────────→ /convert
├── Pricing ────────────────────→ /pricing
├── Features ───────────────────→ /features
├── How It Works ────────────────→ /how-it-works
├── FAQ ────────────────────────→ /faq
├── Sign In ────────────────────→ /login
└── Resources ──────────────────→ /blog or /guides

PRICING
│
└── Upgrade ────────────────────→ Login / Dodo Checkout

LOGIN
│
└── Success ────────────────────→ Intended Destination / Dashboard

CONVERT
│
├── Upload ─────────────────────→ Validation
├── Invalid ────────────────────→ Error State
├── Valid ──────────────────────→ Conversion Settings
├── Convert ────────────────────→ Processing
├── Complete ───────────────────→ Result
└── Download ───────────────────→ DOCX download

DASHBOARD
│
├── Convert ────────────────────→ /convert
├── History ────────────────────→ /dashboard/history
├── Usage ──────────────────────→ /dashboard/usage
├── Billing ────────────────────→ /dashboard/billing
├── Settings ───────────────────→ /dashboard/settings
└── Files ──────────────────────→ /dashboard/files

HISTORY
│
└── Conversion ─────────────────→ Detail

DETAIL
│
├── Download ───────────────────→ DOCX
├── Retry ──────────────────────→ New processing job
├── Review ─────────────────────→ Issues
└── Delete ─────────────────────→ History
```

---

# 70. Conversion State Machine

```text
                  ┌──────────────┐
                  │   UPLOADED   │
                  └──────┬───────┘
                         ↓
                  ┌──────────────┐
                  │   VALIDATING │
                  └──────┬───────┘
                         ↓
                  ┌──────────────┐
                  │    QUEUED    │
                  └──────┬───────┘
                         ↓
                  ┌──────────────┐
                  │  ANALYZING   │
                  └──────┬───────┘
                         ↓
                  ┌──────────────┐
                  │  PROCESSING  │
                  └──────┬───────┘
                         ↓
                  ┌──────────────┐
                  │ RECONSTRUCTING│
                  └──────┬───────┘
                         ↓
                  ┌──────────────┐
                  │  VERIFYING   │
                  └──────┬───────┘
                         │
                ┌────────┴────────┐
                ↓                 ↓
         ┌──────────────┐  ┌──────────────┐
         │   REPAIRING  │  │   FINALIZING │
         └──────┬───────┘  └──────┬───────┘
                │                 │
                └────────┬────────┘
                         ↓
                  ┌──────────────┐
                  │  COMPLETED   │
                  └──────────────┘

At most stages:
                         ↓
                    ┌────────┐
                    │ FAILED │
                    └────────┘
```

---

# 71. UX Principles for the Entire Flow

## Principle 1 — Always show the next useful action

The user should never wonder:

> “What do I click now?”

Every major state must have a clear primary action.

## Principle 2 — Never hide usage information

Users should understand how many pages/verification credits a conversion will consume before starting it.

## Principle 3 — Never fake progress

If exact percentage is unavailable, use meaningful stage-based progress.

## Principle 4 — Preserve work

Refreshing the page or closing the browser should not unnecessarily destroy processing.

## Principle 5 — Make errors actionable

Every common error should explain:

- what happened
- why it happened where known
- what the user can do next

## Principle 6 — Keep conversion central

The product is a conversion tool, not a dashboard product. The dashboard should support conversion rather than distract from it.

---

# 72. Final Ideal User Journey

The ideal first-time experience is:

```text
Google / Direct / Referral
        ↓
Homepage
        ↓
"This is exactly what I need"
        ↓
Convert a PDF Free
        ↓
Upload PDF
        ↓
Validation
        ↓
Choose Standard / Verified
        ↓
Convert
        ↓
Processing
        ↓
Document ready
        ↓
Download Word
        ↓
"That actually preserved my equations."
        ↓
Create account / continue with account
        ↓
Dashboard
        ↓
History + Usage
        ↓
Return when needed
        ↓
Eventually upgrade to Pro/Power
```

The product should make this path extremely short, clear, and trustworthy.

---

# 73. Requirement for Future Implementations

When implementing any new page or interaction, the developer/AI agent must answer:

1. What page is the user currently on?
2. What action did the user take?
3. What state changes?
4. What happens next?
5. Which route/state is shown?
6. What happens if the action fails?
7. What happens if the user lacks permission or usage?
8. Can the user recover without losing work?

No feature should be implemented as an isolated screen.

Every feature must have a complete user flow.

---

# 74. Relationship to Other Project Documents

This document should be used together with:

```text
PRD.md
architecture.md
```

`PRD.md` defines what the product must do.

`architecture.md` defines how the system is built.

`user-flow.md` defines how the user moves through that system.

All three documents must remain consistent.

If a future requirement conflicts with this flow specification, update the flow document before implementation.
