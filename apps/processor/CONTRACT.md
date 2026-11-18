# Processor contract — `document-contract-v1` (architecture §46)

## Input (queue message → processor)

```json
{
  "jobId": "...",
  "sourceArtifactId": "...",
  "mode": "standard|verified",
  "pageRange": null,
  "limits": { "maxPages": 500, "maxVerificationPages": 50 }
}
```

## Output (processor → queue → web)

```json
{
  "jobId": "...",
  "status": "completed",
  "artifactId": "...",
  "metrics": { "pages": 20, "equations": 101, "figures": 12, "tables": 8 },
  "quality": { "verifiedPages": 18, "issues": 2 }
}
```

 workers must never import web internals; web must never import processor
internals. This file is the only coupling point.
