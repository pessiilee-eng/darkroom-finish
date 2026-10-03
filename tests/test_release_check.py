import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_check', ROOT / 'scripts/release_check.py')
checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)


class ReleaseCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'release-files.json').write_text(json.dumps(['release-files.json', 'README.md']))
        (self.root / 'README.md').write_text('A clean public package.')

    def test_clean_files_pass(self):
        self.assertEqual(len(checker.check(self.root)), 2)

    def test_unlisted_photo_rejected(self):
        (self.root / 'private.dng').write_bytes(b'not a real photograph')
        with self.assertRaisesRegex(ValueError, 'Allowlist mismatch'):
            checker.check(self.root)

    def test_personal_path_and_outside_link_rejected(self):
        for text in ('/' + 'Users/' + 'example-person/private-photo', '[outside](../../unavailable)'):
            (self.root / 'README.md').write_text(text)
            with self.assertRaises(ValueError):
                checker.check(self.root)

    def test_symlink_rejected(self):
        (self.root / 'alias').symlink_to(self.root / 'README.md')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            checker.check(self.root)


if __name__ == '__main__':
    unittest.main()
