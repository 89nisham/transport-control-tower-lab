# Factory Closeout

Transport Control Tower Lab v1.0.0 closes the local-first factory for Products 1-13. The repo now ships a coherent file-based toolkit for cleaning transport inputs, reconstructing operational evidence, generating exception packs, and rolling them into one daily management brief.

## What Was Shipped

- 13 local-first transport control-tower micro-products.
- Synthetic demo data for product walkthroughs and tests.
- Streamlit apps for Products 2-13.
- CLI coverage for Trip Sheet Doctor and TowerBrief.
- Deterministic CSV, Excel, Markdown, and HTML outputs where relevant.
- Public-safe docs, screenshots, product notes, and shipping log entries.

No Product 14, SaaS layer, auth, database, paid API, BI server, messaging integration, email integration, or live production connector is included in this release.

## Product Table

| # | Product | Main output | Run command |
|---|---|---|---|
| 1 | Trip Sheet Doctor | Exception workbook | `uv run control-tower trip-sheet-doctor data/samples/trip_sheet_doctor_sample.csv data/output/trip_sheet_doctor_demo.xlsx` |
| 2 | GeoReplay | Visit events and GPS exceptions | `uv run streamlit run georeplay/app.py` |
| 3 | ETA Watch | ETA risk board | `uv run streamlit run eta_watch/app.py` |
| 4 | DetentionClock | Detention report | `uv run streamlit run detention_clock/app.py` |
| 5 | GateTruth | Gate evidence report | `uv run streamlit run gate_truth/app.py` |
| 6 | FuelGuard | Fuel reconciliation report | `uv run streamlit run fuel_guard/app.py` |
| 7 | UpdatePulse | Update discipline report | `uv run streamlit run update_pulse/app.py` |
| 8 | DelayLens | Delay classification report | `uv run streamlit run delay_lens/app.py` |
| 9 | PODPulse | POD aging report | `uv run streamlit run pod_pulse/app.py` |
| 10 | LaneLab | Lane baselines | `uv run streamlit run lane_lab/app.py` |
| 11 | BanWindow | Ban risk board | `uv run streamlit run ban_window/app.py` |
| 12 | CarrierScore | Carrier scorecard | `uv run streamlit run carrier_score/app.py` |
| 13 | TowerBrief | Daily control-tower brief | `uv run streamlit run tower_brief/app.py` or `uv run tower-brief tower_brief/demo_data tower_brief/output` |

## How The Products Connect

Trip Sheet Doctor cleans trip context. GeoReplay turns GPS pings into visits. ETA Watch, DetentionClock, GateTruth, FuelGuard, UpdatePulse, DelayLens, PODPulse, LaneLab, and BanWindow each create focused exception outputs. CarrierScore summarizes carrier performance from trip and exception files. TowerBrief consolidates the product outputs into one daily action-ranked management brief.

Data-flow map:

```text
Trip Sheet Doctor -> GeoReplay -> ETA Watch -> DetentionClock ->
GateTruth -> FuelGuard -> UpdatePulse -> DelayLens -> PODPulse ->
LaneLab -> BanWindow -> CarrierScore -> TowerBrief
```

## Validation Status

Factory validation is based on:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run python - <<'PY'
import py_compile
import subprocess
files = subprocess.check_output(["git", "ls-files", "*.py"], text=True).splitlines()
for file in files:
    py_compile.compile(file, doraise=True)
print(f"Compiled {len(files)} Python files")
PY
uv run tower-brief tower_brief/demo_data tower_brief/output
```

GitHub Actions CI must pass on `main` after the release commit and tags are pushed.

## Known Limitations

- Local files only; no live TMS, telematics, GPS, ERP, fuel-card, email, WhatsApp, Telegram, BI, auth, or database integration.
- Demo data is synthetic and does not represent any real company.
- Product outputs depend on uploaded file quality, column coverage, and timestamp consistency.
- GeoReplay still uses a simple point/geofence matching approach that should be optimized before large GPS datasets.
- BanWindow uses uploaded restriction-window data only and does not provide legal advice.
- TowerBrief is deterministic and does not use AI-generated narrative.

## Post-Factory Backlog

See [post-factory-backlog.md](post-factory-backlog.md) for the intentionally deferred work. The main themes are GeoReplay performance, GitHub Actions maintenance, dispatcher usability, pilot hardening, and security hardening.

## Recommended Pilot Path

1. Start with one synthetic demo run per product to confirm the local environment.
2. Pick one real workflow with public-safe or anonymized files, usually Trip Sheet Doctor -> GeoReplay -> ETA Watch.
3. Add one operational output at a time into TowerBrief.
4. Review outputs with dispatch, billing, and transport managers before adding new integrations.
5. Only after file-based value is proven, decide whether a production connector, database, or alerting workflow is worth building.
