# Phase 5 Prospect Scoring UI Contract

Location: existing Model Training workspace. Audience Explorer remains disabled.

Show scoreability, model run/primary/artifact/feature contract/universe, `Score Prospect Universe` CTA, active job progress, and completed aggregate cards (scored count, range, mean, runtime, throughput).

If canonical completed scoring exists, show it and do not offer duplicate default scoring.

Required language: scores are relative look-alike affinity scores, not guaranteed purchase probabilities.

No person IDs, person rows, individual scores, demographic filters, top-N labels, percentiles, bands, audience selection or export.

Any active training/scoring job disables both Train and Score CTAs. Poll ~1.5–2s and stop terminally. Use safe DOM operations.
