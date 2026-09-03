# Step 12 — DIRECT_MAIL Campaign, Export & CSV Security

Create a second campaign through UI with DIRECT_MAIL channel, exercising selector/draft/review/finalize controls.

Trigger browser download through UI.

Validate exact DIRECT_MAIL_CONTACT_V1 headers, required address fields, optional names, allowed model/rank fields and absence of email/phone/ethnicity/religion/family income/occupation industry where prohibited.

Reconcile selected/deliverable/undeliverable/exported rows and CSV SHA.

Run dedicated security fixtures for values beginning with = + - @ plus commas, quotes, embedded newlines and Unicode. Do not corrupt fresh canonical data merely to inject fixtures.

Verify finalized campaign cannot be edited. STOP.
