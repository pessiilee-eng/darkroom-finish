import importlib.util
from pathlib import Path
import tempfile
import unittest

try:
    from PIL import Image, ImageCms
except ImportError:
    Image = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(Image is None, 'Optional Pillow preview dependency is not installed')
class PreviewTests(unittest.TestCase):
    def test_metadata_stripped_profile_and_pixels_preserved(self):
        spec = importlib.util.spec_from_file_location('preview', ROOT / 'scripts/preview.py')
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / 'input.jpg', Path(temp) / 'output.jpg'
            image = Image.new('RGB', (2000, 1000), (120, 80, 50))
            exif = Image.Exif(); exif[315] = 'Synthetic privacy test'; exif[270] = 'DO NOT COPY'
            exif[34853] = {1: 'N', 2: (1.0, 2.0, 3.0), 3: 'E', 4: (4.0, 5.0, 6.0)}
            xmp = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><private>synthetic GPS metadata test</private></x:xmpmeta>'
            image.save(source, exif=exif, xmp=xmp, icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes(), comment=b'private')
            with Image.open(source) as challenge:
                self.assertTrue(challenge.getexif().get_ifd(34853))
                self.assertEqual(challenge.info.get('xmp'), xmp)
            before = source.read_bytes()
            result = mod.preview(source, output)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(result['dimensions'], [1600, 800])
            self.assertFalse(result['uploaded'])
            with Image.open(output) as check:
                self.assertEqual(dict(check.getexif()), {})
                self.assertNotIn('comment', check.info)
                self.assertNotIn('xmp', check.info)
                self.assertGreater(sum(check.getpixel((100, 100))), 0)
            with self.assertRaises(ValueError):
                mod.preview(source, output)


if __name__ == '__main__':
    unittest.main()
