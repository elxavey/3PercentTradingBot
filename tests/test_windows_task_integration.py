"""Phase 1.8 task integration contract checks, platform-independent.

These validate launcher/installer wiring but do not execute Windows Task
Scheduler; operational registration must be tested on Windows by the user.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "scripts" / "install_windows_task.ps1").read_text(encoding="utf-8")
LAUNCH = (ROOT / "scripts" / "run_scheduled_scan.ps1").read_text(encoding="utf-8")


class WindowsTaskIntegrationTests(unittest.TestCase):
    def test_installer_is_opt_in_and_supports_whatif(self):
        self.assertIn("SupportsShouldProcess = $true", INSTALL)
        self.assertIn("$PSCmdlet.ShouldProcess(", INSTALL)
        self.assertIn("Register-ScheduledTask", INSTALL)

    def test_installer_does_not_overwrite_existing_task(self):
        self.assertNotIn("-Principal $principal -Force", INSTALL)

    def test_installer_uses_nonoverlap_setting(self):
        self.assertIn("-MultipleInstances IgnoreNew", INSTALL)
        self.assertIn("-StartWhenAvailable:$false", INSTALL)

    def test_installer_runs_as_current_interactive_user(self):
        self.assertIn("-LogonType Interactive", INSTALL)
        self.assertIn("-RunLevel Limited", INSTALL)

    def test_installer_does_not_start_worker_directly(self):
        self.assertIn("run_scheduled_scan.ps1", INSTALL)
        self.assertIn("-EncodedCommand", INSTALL)
        self.assertNotIn("tradepilot.worker", INSTALL)

    def test_launcher_runs_one_shot_scheduler(self):
        self.assertIn("-m tradepilot.scheduler --universe $Universe", LAUNCH)
        self.assertNotIn("--loop", LAUNCH)
        self.assertNotIn("tradepilot.worker", LAUNCH)

    def test_launcher_writes_diagnostic_log(self):
        self.assertIn("windows_scheduler.log", LAUNCH)
        self.assertIn("$LASTEXITCODE", LAUNCH)

    def test_installer_requires_virtualenv(self):
        self.assertIn(".venv\\Scripts\\python.exe", INSTALL)
        self.assertIn("Test-Path -LiteralPath $python", INSTALL)


if __name__ == "__main__":
    unittest.main()
