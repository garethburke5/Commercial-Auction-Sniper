from pathlib import Path
import unittest


class BoardStabilityTests(unittest.TestCase):
    def test_wrapper_does_not_install_pagination_renderer_hooks(self):
        app = Path("app.py").read_text(encoding="utf-8")
        self.assertNotIn("st.markdown = _paged_markdown", app)
        self.assertNotIn("st.caption = _paged_caption", app)
        self.assertNotIn("_BOARD_PAGINATION", app)

    def test_board_paginates_filtered_lots_before_card_generation(self):
        board = Path("legacy_app.py").read_text(encoding="utf-8")
        self.assertIn('page_choice=st.selectbox(', board)
        self.assertIn('["10","50","100","All"]', board)
        self.assertIn('lots=lots[start:end]', board)
        self.assertIn('window=page_window(current_page,pages,max_buttons=7)', board)

    def test_source_health_accepts_note_or_message(self):
        board = Path("legacy_app.py").read_text(encoding="utf-8")
        self.assertIn('h.get("note") or h.get("message") or ""', board)


if __name__ == "__main__":
    unittest.main()
