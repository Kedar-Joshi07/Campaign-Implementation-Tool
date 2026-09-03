# Step 5 — Prompts, Evidence, Security & Code Hygiene

Classify prompts as CURRENT/COMPLETED/SUPERSEDED/HISTORICAL/DO NOT RUN and evidence as CURRENT AUTHORITATIVE/SUPPORTING/HISTORICAL/SUPERSEDED/DEBUG.

Search for dead imports, debug prints, hardcoded local paths, completed TODO residue, commented temporary code, obsolete phase gates, stale Coming Soon flags and duplicate constants. Remove only obvious housekeeping residue.

Scan for .env, tokens, passwords, certificates, real production data and accidentally committed exports. Do not upload secrets externally. STOP.
