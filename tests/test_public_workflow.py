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

    def knowledge_plan(self, parameters):
        library = self.root / 'knowledge/library'
        _, catalog, _ = cli.knowledge.load(library)
        chosen = catalog['packages'][0]
        kp = cli.knowledge.template(library, chosen['id'], self.receipt['source_id'])
        kp.update(source_observation='Synthetic unit-test statements; not a photograph review.',
                  intent='Synthetic compiler test', reference_limit='Offline structural test; no artwork viewed.')
        for key in ('required', 'incompatible'):
            for row in kp['fit'][key]:
                row.update(matches=key == 'required', observation='Synthetic assertion for compiler unit testing only.')
        for row in kp['references']:
            row['observation'] = 'No reference opened in this offline unit test.'
        for row in kp['relations']:
            mids = [m['id'] for m in chosen['methods'] if row['id'] in m['relation_ids']]
            row.update(decision='adjust' if row['id'] == 'light' else 'preserve',
                       observation='Synthetic test relation', target='Synthetic test target', method_ids=mids[:1])
        registry = json.loads((self.root / 'registries/adobe-operation-registry-v1.json').read_text())
        baseline = {**cli.knowledge.NEUTRAL, **parameters}
        for op in cli.knowledge.changed_operations(baseline, None, None, registry):
            kp['operations'].append({'operation_id': op, 'basis': 'image_specific', 'method_ids': [],
                                     'relation_ids': ['light'], 'rationale': 'Synthetic numeric test, not artist attribution.'})
        p = self.base / 'knowledge-plan.json'; p.write_text(json.dumps(kp))
        return p

    def plan(self, parameters=None):
        parameters = parameters or {'exposure2012': '0.5'}
        p = self.base / 'params.json'
        p.write_text(json.dumps(parameters))
        kp = self.knowledge_plan(parameters)
        return cli.prepare(str(self.root), self.receipt['source_id'], str(p), 'Synthetic compiler test', str(kp))

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
        self.assertEqual(sorted(x.name for x in self.base.iterdir()), ['knowledge-plan.json', 'params.json', 'source.dng', 'workspace with space'])

    def test_no_symlinks_or_path_escape(self):
        link = self.base / 'linked.dng'
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            cli.ingest(str(self.root), str(link), 'fixture')
        for name in ('../escape', '/tmp/escape'):
            with self.assertRaises(ValueError):
                cli.local_path(self.root, name)

    def test_write_directories_cannot_redirect_private_data(self):
        for folder in ('staging', 'runs', 'knowledge/cards'):
            fresh = self.base / ('workspace-' + folder.replace('/', '-'))
            cli.init_workspace(str(fresh))
            outside = self.base / ('outside-' + folder.replace('/', '-')); outside.mkdir()
            (fresh / folder).symlink_to(outside, target_is_directory=True)
            if folder == 'knowledge/cards':
                receipt = cli.ingest(str(fresh), str(self.source), 'Synthetic fixture only.')
                with self.assertRaises(ValueError):
                    cli.prepare(str(fresh), receipt['source_id'], str(ROOT / 'examples/neutral.json'), 'Test', role='baseline')
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

    def test_edit_requires_source_bound_knowledge(self):
        with self.assertRaisesRegex(ValueError, 'Knowledge plan required'):
            cli.prepare(str(self.root), self.receipt['source_id'], str(ROOT / 'examples/exposure-probe.json'), 'No knowledge')

    def test_baseline_and_probe_cannot_bypass_knowledge(self):
        for role in ('baseline', 'probe'):
            with self.assertRaises(ValueError):
                cli.prepare(str(self.root), self.receipt['source_id'], str(ROOT / 'examples/exposure-probe.json'), 'Bypass', role=role)

    def test_knowledge_mutation_stops_existing_workspace(self):
        (self.root / 'knowledge/library/index.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Knowledge changed'):
            cli.workspace(str(self.root))

    def test_exact_relationships_and_operations_required(self):
        params = {'exposure2012': '0.5'}
        path = self.knowledge_plan(params)
        kp = json.loads(path.read_text())
        for change in ('source', 'method', 'operation', 'relation', 'fit', 'visual'):
            bad = json.loads(json.dumps(kp))
            if change == 'source': bad['source_sha256'] = '0' * 64
            if change == 'method': bad['relations'][0]['method_ids'] = ['imaginary']
            if change == 'operation': bad['operations'] = []
            if change == 'relation': bad['relations'] = bad['relations'][:-1]
            if change == 'fit': bad['fit']['required'][0]['matches'] = False
            if change == 'visual': bad['mode'] = 'visual_reference'
            with self.subTest(change=change), self.assertRaises(ValueError):
                cli.knowledge.validate_plan(self.root / 'knowledge/library', bad, self.receipt['source_id'], ['acr.exposure2012'])

    def test_receipt_is_bound_by_actual_compiler(self):
        result = self.plan()
        plan = json.loads((self.root / result['plan']).read_text())
        paths = {r['path'] for r in plan['binding']['dependencies']}
        self.assertIn(result['knowledge_receipt'], paths)
        self.assertIn('knowledge/library/manifest.json', paths)
        receipt = self.root / result['knowledge_receipt']
        data = json.loads(receipt.read_text()); data['parameters']['exposure2012'] = '0.75'
        receipt.write_text(json.dumps(data))
        script = 'from pathlib import Path; import json; from darkroom.local_trial import verify_binding; verify_binding(Path.cwd(),json.loads(Path(' + repr(str(self.root / result['plan'])) + ').read_text()))'
        run = subprocess.run([sys.executable, '-B', '-c', script], cwd=self.root, capture_output=True)
        self.assertNotEqual(run.returncode, 0)


if __name__ == '__main__':
    unittest.main()
