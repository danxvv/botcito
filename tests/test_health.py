"""Check the heartbeat behind the container health check, and yt-dlp age warnings."""

import shutil
import subprocess
import sys
import time
from datetime import date

import pytest

import health


def test_fresh_heartbeat_is_healthy(tmp_path):
    path = tmp_path / "data" / "heartbeat"
    health.write_heartbeat(path)
    assert path.exists()
    assert health.is_healthy(path)


def test_missing_corrupt_or_stale_heartbeats_are_unhealthy(tmp_path):
    path = tmp_path / "heartbeat"
    assert not health.is_healthy(path)
    path.write_text("not a number")
    assert not health.is_healthy(path)
    path.write_text("")
    assert not health.is_healthy(path)
    path.write_text("1000.0")
    assert health.is_healthy(path, now=1000 + health.MAX_HEARTBEAT_AGE - 1)
    assert not health.is_healthy(path, now=1000 + health.MAX_HEARTBEAT_AGE)


def test_an_old_heartbeat_can_be_cleared(tmp_path):
    path = tmp_path / "heartbeat"
    health.write_heartbeat(path)
    health.clear_heartbeat(path)
    assert not path.exists() and not health.is_healthy(path)
    health.clear_heartbeat(path)  # Clearing twice is fine.


def test_heartbeat_outlasts_missed_beats():
    assert health.MAX_HEARTBEAT_AGE >= 2 * health.HEARTBEAT_INTERVAL


def test_health_check_script_exit_code_follows_the_heartbeat(tmp_path):
    # `python health.py` is what the compose healthcheck runs. Run a copy from a temporary
    # folder, where it looks for data/heartbeat, so the real data folder is never touched.
    script = tmp_path / "health.py"
    shutil.copy(health.__file__, script)
    run = lambda: subprocess.run([sys.executable, str(script)], cwd=tmp_path).returncode
    assert run() == 1
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "heartbeat").write_text(str(time.time()))
    assert run() == 0
    (tmp_path / "data" / "heartbeat").write_text(str(time.time() - health.MAX_HEARTBEAT_AGE - 1))
    assert run() == 1


@pytest.mark.parametrize(
    "version, today, expected",
    [
        ("2026.08.19", date(2026, 8, 19), 0),
        ("2026.8.19", date(2026, 9, 18), 30),
        ("2026.08.19.232948", date(2026, 8, 20), 1),  # Nightly builds carry a time suffix.
        ("2025.12.31", date(2026, 1, 2), 2),
        ("not-a-version", date(2026, 8, 19), None),
        ("2026.13.40", date(2026, 8, 19), None),
        ("", date(2026, 8, 19), None),
        ("2026.08", date(2026, 8, 19), None),
    ],
)
def test_ytdlp_age_days(version, today, expected):
    assert health.ytdlp_age_days(version, today) == expected
