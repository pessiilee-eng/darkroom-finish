"""No Adobe or private photos: independent workspace, real compiler and guards."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_darkroom', ROOT / 'scripts/darkroom.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class PublicWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='darkroom-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'workspace with space'
        cli.init_workspace(str(self.root))
        self.source = self.base / 'source.dng'
        self.source.write_bytes(b'synthetic-placeholder-not-a-photograph')
        self.receipt = cli.ingest(str(self.root), str(self.source), 'Use this test file locally.')

    def plan(self, parameters=None):
        p = self.base / 'params.json'
        p.write_text(json.dumps(parameters or {'exposure2012': '0.5'}))
        return cli.prepare(str(self.root), self.receipt['source_id'], str(p), 'Synthetic compiler test')

    def test_compiler_in_independent_workspace(self):
        result = self.plan()
        plan = json.loads((self.root / result['plan']).read_text())
        self.assertEqual(plan['binding']['parameters']['Exposure2012'], '0.5')
        self.assertEqual(plan['binding']['parameters']['WhiteBalance'], 'As Shot')
        self.assertFalse(plan['quality_acceptance_passed'])
        self.assertEqual(cli.sha(self.source), self.receipt['source_id'])

    def test_no_overwrite_workspace_or_source(self):
        with self.assertRaises(ValueError):
            cli.init_workspace(str(self.root))
        before = self.source.read_bytes()
        self.plan()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(sorted(x.name for x in self.base.iterdir()), ['params.json', 'source.dng', 'workspace with space'])

    def test_no_symlinks_or_path_escape(self):
        link = self.base / 'linked.dng'
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            cli.ingest(str(self.root), str(link), 'fixture')
        for name in ('../escape', '/tmp/escape'):
            with self.assertRaises(ValueError):
                cli.local_path(self.root, name)

    def test_write_directories_cannot_redirect_private_data(self):
        for folder in ('staging', 'runs', 'knowledge'):
            fresh = self.base / ('workspace-' + folder)
            cli.init_workspace(str(fresh))
            outside = self.base / ('outside-' + folder); outside.mkdir()
            (fresh / folder).symlink_to(outside, target_is_directory=True)
            if folder == 'knowledge':
                receipt = cli.ingest(str(fresh), str(self.source), 'Synthetic fixture only.')
                with self.assertRaises(ValueError):
                    cli.prepare(str(fresh), receipt['source_id'], str(ROOT / 'examples/neutral.json'), 'Test')
            else:
                with self.assertRaises(ValueError):
                    cli.ingest(str(fresh), str(self.source), 'Synthetic fixture only.')
            self.assertEqual(list(outside.iterdir()), [])

    def test_original_change_stops_before_plan(self):
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Original changed'):
            self.plan()

    def test_runtime_change_refused(self):
        (self.root / 'darkroom/local_trial.py').write_text('modified')
        with self.assertRaisesRegex(ValueError, 'Runtime changed'):
            cli.workspace(str(self.root))

    def test_unknown_field_refused(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            self.plan({'invented_effect': '1'})

    def test_bad_value_and_out_of_range_refused(self):
        for value in ('99', 'NaN', '0.50'):
            with self.assertRaises(subprocess.CalledProcessError):
                self.plan({'exposure2012': value})

    def test_attempt_budget_not_reset_by_new_plan_name(self):
        for _ in range(3):
            self.plan()
        with self.assertRaises(subprocess.CalledProcessError):
            self.plan()

    def test_missing_authorization_refused(self):
        other = self.base / 'other.dng'; other.write_bytes(b'other')
        with self.assertRaises(ValueError):
            cli.ingest(str(self.root), str(other), '')

    def test_cli_does_not_require_original_repository(self):
        result = subprocess.run([sys.executable, '-I', '-B', str(self.root / 'darkroom/ps_acr/card_pipeline.py'), '--help'], cwd=self.base, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == '__main__':
    unittest.main()
