# Business UI Information Architecture

Visible navigation:
- Home
- Find Potential Customers
- Results

Hide from normal UI, but retain code/APIs/tests:
Data Status, Historical Analysis, Model Training & Scoring, Audience Explorer,
legacy Campaigns, analyst Insights, technical Saved Audience views.

Add centralized visibility/view-group metadata so a future RBAC phase can expose them to
ADMIN/DATA_ANALYST/MODEL_ADMIN without rebuilding navigation.

Home:
business-safe KPIs, recent results, CTA.

Find Potential Customers:
one clean form with Campaign Details, Campaign Context, Targeting Preferences,
Delivery/Export Profile and one primary submit action.

Results:
newest-first immutable run history with campaign name, time, status, criteria summary,
delivery profile, selected count, result_source, duration, View and Download.

Result detail:
full criteria/context, exact counts, profiles, reuse explanation, currentness and technical
details disclosure; no contact PII.
