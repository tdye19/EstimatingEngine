# Completed Backlog Items

- 2026-05-12: Removed admin_diagnostics HTTP router (Spec 19C.1). Ported to CLI per audit: seed-gap-findings subcommand has unique diagnostic value, moved to apex/backend/scripts/admin_diagnostics_cli.py.
- 2026-05-12: size_sf zombie column removed from projects table (Spec HF-29). Path B: canonical field is Project.square_footage. Migration c4e8a1f2d9b7 drops projects.size_sf. Fixed decision_benchmark.py and decision.py to use square_footage. ComparableProject.size_sf untouched.
