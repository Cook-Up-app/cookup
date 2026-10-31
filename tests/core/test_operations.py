import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = [ROOT / "scripts" / "backup.sh", ROOT / "scripts" / "restore.sh"]


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash n'est pas installé")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_scripts_are_valid_shell(script):
    result = subprocess.run(
        [shutil.which("bash"), "-n", str(script)], capture_output=True, text=True, check=False
    )  # noqa: S603

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_passphrase_never_appears_on_a_command_line(script):
    text = script.read_text()

    assert "-pass env:BACKUP_PASSPHRASE" in text
    assert "pass:" not in text.replace("-pass env:", "")


def test_scripts_stop_on_error_and_demand_their_secrets():
    for script in SCRIPTS:
        text = script.read_text()
        assert "set -euo pipefail" in text and ":?" in text


def test_backup_workflow_is_weekly_encrypted_and_skips_without_secrets():
    text = (ROOT / ".github" / "workflows" / "backup.yml").read_text()

    assert 'cron: "0 3 * * 0"' in text and "retention-days: 90" in text
    assert "secrets.BACKUP_PASSPHRASE" in text and "sauvegarde ignorée" in text
    assert "postgres:17-alpine" in text  # client aligné sur le serveur Supabase


def test_import_workflow_and_vercel_crons_are_consistent():
    vercel = (ROOT / "vercel.json").read_text()
    assert "/internal/cron/daily" in vercel and "/internal/cron/import" in vercel
