import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('prune_releases', Path(__file__).parents[1] / 'deploy/cloud/prune-releases.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReleaseRetentionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.releases = self.root / 'releases'
        self.releases.mkdir()
        self.versions = []
        for i in range(6):
            item = self.releases / f'version-{i}'
            item.mkdir()
            (item / 'index.html').write_text('release')
            os.utime(item, (100 + i, 100 + i))
            self.versions.append(item)
        (self.root / 'current').symlink_to(self.versions[0])

    def tearDown(self):
        self.temp.cleanup()

    def test_keeps_current_previous_and_newest_even_when_current_is_oldest(self):
        module.prune(self.root, self.versions[1], apply=True)
        remaining = {path.name for path in self.releases.iterdir()}
        self.assertEqual(remaining, {'version-0', 'version-1', 'version-5'})
        self.assertTrue((self.root / 'current/index.html').is_file())

    def test_default_is_dry_run(self):
        self.assertEqual(len(module.prune(self.root)), 3)
        self.assertEqual(len(list(self.releases.iterdir())), 6)

    def test_never_follows_external_symlinks(self):
        outside = self.root / 'external-data'
        outside.mkdir()
        (outside / 'keep').write_text('protected')
        (self.releases / 'external').symlink_to(outside, target_is_directory=True)
        module.prune(self.root, apply=True)
        self.assertTrue((outside / 'keep').is_file())
        self.assertTrue((self.releases / 'external').is_symlink())

    def test_invalid_current_stops_cleanup(self):
        (self.root / 'current').unlink()
        with self.assertRaises(ValueError):
            module.prune(self.root, apply=True)
        self.assertEqual(len(list(self.releases.iterdir())), 6)


if __name__ == '__main__':
    unittest.main()
