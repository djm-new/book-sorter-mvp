import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "books_sorter.html").read_text(encoding="utf-8")


class SampleSpecTests(unittest.TestCase):
    def test_sample_photos_have_per_image_crop_specs(self):
        """Bundled photos must not be treated as five whole-photo cards."""
        marker = "const SAMPLE_BOOK_SPECS_BY_FILE = {"
        self.assertIn(marker, HTML)
        sample_keys = re.findall(r'"sample-0[1-5]\.jpg"\s*:', HTML)
        self.assertEqual(len(sample_keys), 5)

    def test_sample_specs_cover_real_book_count(self):
        specs = re.findall(r'\{\s*title:\s*"[^"]+",\s*x:\s*\d+,\s*y:\s*\d+,\s*w:\s*\d+,\s*h:\s*\d+', HTML)
        # The five supplied sample photos contain many individual books/items;
        # regression guard against detecting only the five source photos.
        self.assertGreaterEqual(len(specs), 70)

    def test_known_wood_only_crops_are_removed(self):
        self.assertNotIn('title: "New York for Kids"', HTML)
        self.assertNotIn('title: "Travel Puzzles", x: 275, y: 1075', HTML)
        self.assertNotIn('title: "Little Words", x: 485, y: 1075', HTML)
        self.assertNotIn('title: "Paper Mache", x: 720, y: 1080', HTML)

    def test_sample_labels_use_image_specific_specs_before_detector_fallback(self):
        self.assertIn("const sampleSpecs = sampleSpecsForLabel(label);", HTML)
        self.assertIn("if (sampleSpecs) {", HTML)
        self.assertIn("return buildSampleGroups(canvas, sampleSpecs, label);", HTML)
        self.assertIn("const hash = averageHash(stats.crop);", HTML)
        self.assertNotIn("replace(/[^a-z0-9]+/gi", HTML)


if __name__ == "__main__":
    unittest.main()
