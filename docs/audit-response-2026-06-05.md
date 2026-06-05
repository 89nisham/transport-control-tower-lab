# Audit Response - 2026-06-05

## Summary

An independent audit flagged two reported runtime typo risks in ETA Watch and DetentionClock, plus the absence of a GitHub Actions CI/CD gate. Product development was paused to isolate a stability hotfix from the local Product 5 and Product 6 commits.

## Accepted Findings

- Missing CI/CD was a valid stability gap.
- Added `.github/workflows/ci.yml` with dependency sync, pytest, Ruff, and compilation of every tracked Python file.
- Added regression coverage around the audited ETA and DetentionClock execution paths.

## Disputed Findings

- The reported `board.locas_signal` typo was verified absent from `eta_watch/engine.py`.
- The reported `source.locissing_dwell` typo was verified absent from `detention_clock/engine.py`.
- New tests prove the relevant paths execute successfully:
  - `test_has_signal_path_calculates_predicted_eta_and_delta`
  - `test_missing_dwell_minutes_value_is_imputed_from_enter_and_exit`
  - `test_missing_exit_with_missing_dwell_column_does_not_crash`

## Additional Stability Work

- Missing required CSV columns now surface as readable `ValueError` messages.
- ETA Watch and DetentionClock Streamlit apps catch schema `ValueError` failures and show the message in the UI instead of exposing raw tracebacks.

## Remaining Backlog

- GeoReplay performance tuning remains a backlog item for larger GPS files.
