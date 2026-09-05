import unittest

from run_collectors import _remove_duplicate_images


class DuplicateImageQualityTests(unittest.TestCase):
    def test_repeated_source_image_is_removed(self):
        shared = "https://example.com/uploads/default-property.jpg"
        rows = [
            {"source": "Acuitus", "url": f"https://example.com/property/{i}", "image_url": shared}
            for i in range(3)
        ]
        removed, duplicate_urls = _remove_duplicate_images(rows)
        self.assertEqual(removed, 3)
        self.assertEqual(duplicate_urls["Acuitus"][shared], 3)
        self.assertTrue(all(row["image_url"] is None for row in rows))

    def test_two_matching_images_are_not_assumed_generic(self):
        shared = "https://example.com/uploads/shared-building.jpg"
        rows = [
            {"source": "Example", "url": "https://example.com/a", "image_url": shared},
            {"source": "Example", "url": "https://example.com/b", "image_url": shared},
        ]
        removed, duplicate_urls = _remove_duplicate_images(rows)
        self.assertEqual(removed, 0)
        self.assertEqual(duplicate_urls, {})
        self.assertTrue(all(row["image_url"] == shared for row in rows))


if __name__ == "__main__":
    unittest.main()
