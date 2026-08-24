# Phase 5 Security and Privacy Boundary

Scoring may read person_id plus the exact 11 model features only. It must not read name/email/phone/address/postal/city/ethnicity/religion/occupation industry/family income or unrelated demographic fields.

`person_id` + score may be persisted internally because Phase 6 needs them, but Phase 5 public API/UI does not expose individual rows.

Never use customer_id in prospect scoring. Do not log person IDs/raw rows/scores. Logs may contain run/job/model IDs, counts, stage, runtime.

Errors never expose SQL, traceback, absolute artifact/DB path, or raw feature values. Persist/public JSON must reject NaN/Infinity. UI has no individual prospect data.
