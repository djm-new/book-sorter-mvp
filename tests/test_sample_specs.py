import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "books_sorter.html").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "sample-crops" / "manifest.json").read_text(encoding="utf-8"))


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
        self.assertNotIn('title: "ABC Workbook"', HTML)
        self.assertNotIn('title: "New York for Kids"', HTML)
        self.assertNotIn('title: "Travel Puzzles", x: 275, y: 1075', HTML)
        self.assertNotIn('title: "Little Words", x: 485, y: 1075', HTML)
        self.assertNotIn('title: "Paper Mache", x: 720, y: 1080', HTML)

    def test_floor_hue_generated_manifest_drives_sample_set(self):
        self.assertIn('fetch("/sample-crops/manifest.json"', HTML)
        self.assertIn('buildManifestGroups', HTML)
        self.assertEqual(MANIFEST["generatedBy"], "floor-hue-segmentation-v1-title-rotation-overrides")
        self.assertGreaterEqual(len(MANIFEST["items"]), 69)
        self.assertTrue(all(item["src"].startswith("/sample-crops/") for item in MANIFEST["items"]))
        self.assertGreaterEqual(min(item["fill"] for item in MANIFEST["items"]), 0.35)
        self.assertNotIn("01-13", {item["id"] for item in MANIFEST["items"]})
        self.assertEqual(next(item for item in MANIFEST["items"] if item["id"] == "01-02")["title"], "My First Sticker by Numbers")
        self.assertEqual(next(item for item in MANIFEST["items"] if item["id"] == "01-02")["rotation"], 90)

    def test_mobile_ui_is_compact_and_solid_actions(self):
        self.assertIn(".topbar { position: static; }", HTML)
        self.assertIn(".title-wrap p { display: none; }", HTML)
        self.assertIn(".hint-box { display: none; }", HTML)
        self.assertIn("background: linear-gradient(180deg, #22c55e, #16a34a);", HTML)
        self.assertIn("background: linear-gradient(180deg, #ef4444, #dc2626);", HTML)
        self.assertNotIn("rotateBtn.style.background", HTML)

    def test_gallery_and_modal_decision_controls(self):
        self.assertIn("border-radius: 50%;", HTML)
        self.assertIn("aspect-ratio: 1 / 1;", HTML)
        self.assertIn('id="modalImageKeepBtn"', HTML)
        self.assertIn('id="modalImageDiscardBtn"', HTML)
        self.assertIn('id="modalDecisionOverlay"', HTML)
        self.assertIn("formatCategorySubtitle", HTML)
        self.assertIn("renderModalDecisionOverlay", HTML)
        self.assertIn("font-size: clamp(7rem, 32vw, 14rem);", HTML)
        self.assertIn("function toggleDecision(id, decision)", HTML)
        self.assertIn("group.decision === decision ? null : decision", HTML)
        self.assertNotIn('rotateBtn.className = "icon-btn rotate"', HTML)
        self.assertNotIn("rotate 0°", HTML)
        self.assertNotIn("hash ${group.hash", HTML)

    def test_modal_swipe_navigation(self):
        self.assertIn('id="modalImageWrap"', HTML)
        self.assertIn('addEventListener("touchstart"', HTML)
        self.assertIn('addEventListener("touchend"', HTML)
        self.assertIn("function navigateModal(delta)", HTML)
        self.assertIn("navigateModal(dx < 0 ? 1 : -1);", HTML)
        self.assertIn("Swipe left/right", HTML)
        self.assertIn("swipe-edge left", HTML)
        self.assertIn("swipe-edge right", HTML)

    def test_sample_labels_use_image_specific_specs_before_detector_fallback(self):
        self.assertIn("const sampleSpecs = sampleSpecsForLabel(label);", HTML)
        self.assertIn("if (sampleSpecs) {", HTML)
        self.assertIn("return buildSampleGroups(canvas, sampleSpecs, label);", HTML)
        self.assertIn("const hash = averageHash(stats.crop);", HTML)
        self.assertNotIn("replace(/[^a-z0-9]+/gi", HTML)


if __name__ == "__main__":
    unittest.main()
