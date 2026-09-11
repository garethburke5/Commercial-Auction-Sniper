import unittest

from pagination import clamp_page, page_count, page_size_value, page_window, slice_bounds


class PaginationTests(unittest.TestCase):
    def test_standard_page_sizes(self):
        self.assertEqual(page_size_value("10", 557), 10)
        self.assertEqual(page_size_value("50", 557), 50)
        self.assertEqual(page_size_value("100", 557), 100)
        self.assertEqual(page_size_value("All", 557), 557)

    def test_557_results_at_50_per_page(self):
        self.assertEqual(page_count(557, 50), 12)
        self.assertEqual(slice_bounds(557, 50, 1), (0, 50))
        self.assertEqual(slice_bounds(557, 50, 12), (550, 557))

    def test_page_is_clamped_after_filters_reduce_results(self):
        self.assertEqual(clamp_page(12, 83, 50), 2)
        self.assertEqual(slice_bounds(83, 50, 12), (50, 83))

    def test_page_window_starts_with_1_to_7(self):
        self.assertEqual(page_window(1, 12), [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(page_window(4, 12), [1, 2, 3, 4, 5, 6, 7])

    def test_page_window_tracks_middle_and_end(self):
        self.assertEqual(page_window(7, 12), [4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(page_window(12, 12), [6, 7, 8, 9, 10, 11, 12])

    def test_all_is_one_page(self):
        size = page_size_value("All", 557)
        self.assertEqual(page_count(557, size), 1)
        self.assertEqual(slice_bounds(557, size, 1), (0, 557))


if __name__ == "__main__":
    unittest.main()
