# Step 19 — Real System-Browser End-to-End Certification

Use installed Chrome preferred, Edge fallback.

Create dynamic inventory for all Phase11 visible controls.
Allowed terminal statuses: PASS, FAIL, JUSTIFIED_EXCLUSIVE.
No reachable NOT_RUN.

Browser must prove normal user sees only:
Home / Find Potential Customers / Results.

Exercise multi-select component for every main dimension and at least representative advanced fields:
search, multiple checks, deselect, Select All/Clear where applicable, keyboard, Escape, outside click.

Business scenario:
1 Home
2 Find Potential Customers
3 enter campaign
4 multi-select context
5 multi-select targeting
6 choose delivery profile
7 submit
8 observe business progress
9 Results shows completed run
10 View Result
11 Download
12 repeat exact request
13 Results shows second run with exact reuse
14 modify demographic filters
15 third run uses intelligence reuse
16 change delivery profile
17 no model/scoring rebuild
18 create another context requiring new preparation in controlled environment

Test enabled omnichannel downloads in browser, including Paid Social/Search hash-only files.

Test unavailable/gated profile UX if any profile remains unavailable.

Responsive:
1920x1080
1366x768
1024x768
768x1024
390x844

Accessibility:
keyboard, focus, ARIA live processing, dropdown semantics, errors, no color-only status.

Telemetry:
zero unexplained console errors, JS exceptions, critical network failures.

Evidence:
screenshots + coverage JSON + `docs/evidence/phase11/19_SYSTEM_BROWSER_CERTIFICATION.md`

STOP.
