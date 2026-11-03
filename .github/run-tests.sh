#!/bin/sh
# The fast suite as CI runs it. The suite has tests that wait on real processes and timers, and a
# shared CI runner is sometimes slow enough to miss one; the failed tests then run once more, alone.
# A test that passes the second time shows as a warning on the run (so it gets fixed, not hidden),
# and one that fails again fails the job.
set -u
export QT_QPA_PLATFORM=offscreen
if uv run --no-sync pytest -q -o faulthandler_timeout=300; then
  exit 0
fi
failed=$(uv run --no-sync python -c 'import json; print(" ".join(json.load(open(".pytest_cache/v/cache/lastfailed"))))' 2>/dev/null)
echo "Running the failed tests again: $failed"
if uv run --no-sync pytest -q -o faulthandler_timeout=300 --lf; then
  echo "::warning title=Flaky tests::Failed once and passed when run again: $failed"
  exit 0
fi
exit 1
