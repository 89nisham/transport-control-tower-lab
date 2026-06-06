# Post-Factory Backlog

These items are intentionally documented, not implemented, in the v1.0.0 local-first factory closeout.

## 1. GeoReplay Performance Sprint

- Replace the current O(n*m) point/geofence loop with a spatial join.
- Add a benchmark dataset that represents larger GPS exports and geofence masters.
- Add a performance test with a clear runtime threshold for the benchmark path.

## 2. GitHub Actions Maintenance

- Address the Node.js 20 deprecation annotation.
- Update workflow action versions or runner environment when appropriate.
- Keep CI boring: dependency sync, tests, ruff, and compile checks should stay easy to inspect.

## 3. Dispatcher Usability

- Add friendlier schema validation for uploaded files.
- Improve uploaded-file previews so dispatchers can quickly see what TowerBrief and the product apps received.
- Make missing-column errors clearer and more actionable.

## 4. Pilot Hardening

- Add practical input size limits for local app runs.
- Standardize output file naming across products.
- Create a data dictionary for shared fields such as `trip_id`, `vehicle_id`, `customer_name`, `carrier_name`, `risk_bucket`, and `severity`.
- Add a sample pilot checklist for a transport manager or control-tower lead.

## 5. Security Hardening

- Mitigate CSV formula injection in exported spreadsheet-style outputs.
- Review output handling so generated files stay local, predictable, and public-safe.
- Document and enforce a no-secrets policy for demo files, uploads, logs, screenshots, and commits.
