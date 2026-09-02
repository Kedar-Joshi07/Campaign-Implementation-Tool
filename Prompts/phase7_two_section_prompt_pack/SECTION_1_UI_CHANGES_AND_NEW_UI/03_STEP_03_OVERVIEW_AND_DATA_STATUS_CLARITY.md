# Step 3 — Overview & Data Status Clarity

## Overview positive metric
Current overview positive count is campaign-observation grain.
Rename to:
`PU-positive observations`
Help:
`Campaign observations with a confirmed attributed purchase.`

Reserve "Known positive customers" for unique-customer concepts.

## Imports
Change `Last import` -> `Last import attempt`.
Also distinguish the current authoritative/published dataset from the latest attempt.
A failed attempt must not imply current live data is broken.

## Path privacy
Do not display full filesystem paths in ordinary UI.
Show logical source/filename/import ID and safe checksum short form where useful.

## Overview deep reconciliation
Render summary/counts/health independently.
Deep exact data-quality reconciliation may run independently/on refresh.
Do NOT sample/reduce the reconciliation for speed.

Heavy exact checks may take 60–180 sec; the fix is asynchronous/non-blocking UX.

Add tests and STOP.
