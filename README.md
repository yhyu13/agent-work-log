# agent-work-log

Public daily work log, PR/MR progress, and read-only projection of unified agent memory.

- Internal memory source of truth: `UnifiedAgentMemory` (local, not published here).
- This repo publishes only a sanitized public projection.
- Static page: `index.html`, generated with inline data and optional `data/latest.json` refresh.
- Public database downloads: `data/memory-public.sqlite`, `data/memory-public.sql`, `data/latest.json`.

## Boundaries

- No private chat transcripts.
- No local machine paths or credentials.
- Candidate lessons are labeled candidate; they are not approved rules.
- PR/MR metadata is public GitHub metadata.

## Regenerate

```bash
python scripts/build_public.py --memory ../UnifiedAgentMemory/memory.sqlite --prs data/prs_raw.json --days data/days.json
```
