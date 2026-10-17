"""Launcher checks with fake Docker: no containers, network, or real .env changes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCKER = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_CALLS"
case "$*" in
  info) exit "${FAIL_INFO:-0}" ;;
  'compose version') exit 0 ;;
  'compose up '* )
    echo "${BUILD_MESSAGE:-build details}"
    exit "${FAIL_BUILD:-0}" ;;
  'compose exec '* ) exit "${FAIL_READY:-0}" ;;
  'compose port screen 3000') echo '127.0.0.1:3456' ;;
  'compose port memory-screen 3003') echo '127.0.0.1:3459' ;;
  'compose port docs 3002') echo '127.0.0.1:3458' ;;
  'compose ps'|'compose down') exit 0 ;;
  *) exit 1 ;;
esac
'''


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('setup.sh', 'start.sh', '.env.example'):
            shutil.copy(ROOT / name, self.root / name)
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        for name, body in [('docker', DOCKER), ('sleep', '#!/usr/bin/env bash\nexit 0\n')]:
            file = bin_dir / name
            file.write_text(body)
            file.chmod(0o755)
        self.calls = self.root / 'calls'
        self.env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}', 'FAKE_CALLS': str(self.calls)}

    def run_setup(self, *args, **env):
        return subprocess.run(['bash', str(self.root / 'setup.sh'), *args], cwd='/tmp',
                              env={**self.env, **env}, text=True, capture_output=True, timeout=10)

    def test_help_needs_no_docker(self):
        result = self.run_setup('--help', FAIL_INFO='1')
        self.assertEqual(result.returncode, 0)
        self.assertIn('Usage: ./setup.sh', result.stdout)
        self.assertFalse(self.calls.exists())

    def test_unknown_option_fails_before_changes(self):
        self.assertEqual(self.run_setup('--unknown').returncode, 2)
        self.assertFalse((self.root / '.env').exists())

    def test_fresh_install_private_credentials_and_quiet_output(self):
        result = self.run_setup('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('http://localhost:3456', result.stdout)
        self.assertIn('http://localhost:3458', result.stdout)
        self.assertIn('http://localhost:3459', result.stdout)
        self.assertNotIn('build details', result.stdout)
        values = dict(line.split('=', 1) for line in (self.root / '.env').read_text().splitlines()
                      if line and not line.startswith('#'))
        token = values['LIGHTHOUSE_TOKEN'].strip("'")
        operator = values['LIGHTHOUSE_OPERATOR_TOKEN'].strip("'")
        proxy = values['LIGHTHOUSE_PROXY_TOKEN'].strip("'")
        self.assertEqual(len(token), 48)
        self.assertEqual(len(proxy), 48)
        self.assertEqual(len({token, operator, proxy}), 3)
        self.assertNotIn(proxy, result.stdout)
        self.assertIn(token + '=local/you', values['LIGHTHOUSE_DESK_USERS'])
        self.assertNotIn(token, result.stdout)
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / '.lighthouse/setup.log').stat().st_mode & 0o777, 0o600)
        self.assertIn('http://docs:3002/', self.calls.read_text())

    def test_repeat_run_preserves_settings_and_does_not_execute_env(self):
        initial = "LIGHTHOUSE_TOKEN='existing-token'\nLIGHTHOUSE_DESK_USERS=existing-token=acme/me\nLIGHTHOUSE_OPERATOR_TOKEN=existing-operator\nLIGHTHOUSE_PROXY_TOKEN=existing-proxy\nLIGHTHOUSE_MODEL_KEY=private-key\nLIGHTHOUSE_MODEL=custom/model\nUNTRUSTED=$(touch injected)\n"
        (self.root / '.env').write_text(initial)
        result = self.run_setup('--yes', '--no-build')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / '.env').read_text(), initial)
        self.assertFalse((self.root / 'injected').exists())
        self.assertNotIn('private-key', result.stdout + result.stderr)
        self.assertIn('compose up -d\n', self.calls.read_text())
        self.assertNotIn('--build', self.calls.read_text())

    def test_existing_token_gets_missing_local_identity(self):
        (self.root / '.env').write_text("LIGHTHOUSE_TOKEN=kept-token\nLIGHTHOUSE_DESK_USERS=''\n")
        self.assertEqual(self.run_setup('--yes').returncode, 0)
        self.assertIn("LIGHTHOUSE_DESK_USERS='kept-token=local/you'", (self.root / '.env').read_text())

    def test_daemon_failure_does_not_create_config(self):
        result = self.run_setup('--yes', FAIL_INFO='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Docker is not available', result.stderr)
        self.assertFalse((self.root / '.env').exists())

    def test_build_failure_keeps_diagnostics_in_log(self):
        result = self.run_setup('--yes', FAIL_BUILD='1', BUILD_MESSAGE='secret-build-diagnostic')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('secret-build-diagnostic', result.stdout + result.stderr)
        self.assertIn('secret-build-diagnostic', (self.root / '.lighthouse/setup.log').read_text())
        self.assertNotIn('Lighthouse is ready', result.stdout)

    def test_port_conflict_has_specific_recovery(self):
        result = self.run_setup('--yes', FAIL_BUILD='1', BUILD_MESSAGE='port is already allocated')
        self.assertIn('A required port is in use', result.stderr)

    def test_readiness_failure_never_claims_success(self):
        result = self.run_setup('--yes', FAIL_READY='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Lighthouse is ready', result.stdout)
        self.assertIn('services are still starting or unavailable', result.stderr)

    def test_stop_and_status_do_not_build_or_remove_data(self):
        for option in ('--stop', '--status'):
            self.assertEqual(self.run_setup(option).returncode, 0)
        calls = self.calls.read_text()
        self.assertIn('compose down\n', calls)
        self.assertIn('compose ps\n', calls)
        self.assertNotIn('up -d', calls)
        self.assertNotIn(' -v', calls)
        self.assertFalse((self.root / '.env').exists())

    def test_old_entry_point_forwards_options(self):
        result = subprocess.run(['bash', str(self.root / 'start.sh'), '--help'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('Usage: ./setup.sh', result.stdout)


if __name__ == '__main__':
    unittest.main()
