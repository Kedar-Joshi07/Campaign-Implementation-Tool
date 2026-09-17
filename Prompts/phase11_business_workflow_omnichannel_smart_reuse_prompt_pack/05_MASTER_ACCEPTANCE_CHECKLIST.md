# Phase 11 Master Acceptance Checklist

UI:
- [ ] only Home/Find Potential Customers/Results visible
- [ ] legacy UI hidden, not deleted
- [ ] future role-gating seam
- [ ] clean responsive navigation

Multi-select:
- [ ] reusable searchable checkbox dropdown
- [ ] Select All / Clear
- [ ] selected count/chips
- [ ] keyboard/Escape/click-outside
- [ ] ARIA
- [ ] handles large option lists

Search run:
- [ ] every submission persisted immutably
- [ ] exact context/criteria/branch hashes
- [ ] analytical lineage
- [ ] result_source + duration
- [ ] nullable future created_by_user_id

Snapshot:
- [ ] immutable
- [ ] no contact PII
- [ ] exact count/checksum
- [ ] restart-safe
- [ ] repeated identical run can reuse it

Reuse:
- [ ] exact-result reuse
- [ ] intelligence reuse
- [ ] new full build
- [ ] filter/profile changes never rescore
- [ ] stale generation invalidates exact cache
- [ ] no permutation explosion

Omnichannel:
- [ ] Email
- [ ] Direct Mail
- [ ] SMS
- [ ] WhatsApp
- [ ] Telemarketing
- [ ] Paid Social
- [ ] Paid Search
- [ ] Push gated by identifier/consent
- [ ] Display gated
- [ ] Website/On-site gated
- [ ] profile-specific allowlists
- [ ] paid-media hashing
- [ ] audit/checksum/formula mitigation

Results:
- [ ] newest-first history
- [ ] every run visible
- [ ] detail view
- [ ] exact criteria
- [ ] download
- [ ] no PII onscreen

Future learning:
- [ ] exact selected person membership retained
- [ ] generation/model/scoring lineage retained
- [ ] future outcome/feedback seam
- [ ] no false claim of reinforcement learning implemented

Release:
- [ ] Phase1–10 regression
- [ ] bounded clean-room
- [ ] system browser
- [ ] exact-result/intelligence-reuse/new-build certified
- [ ] true full 5M new-context path certified
- [ ] exact-SHA CI
