import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app  # noqa: E402


SAMPLE_ITEM = {
    "id": "lst_test",
    "title": "Vintage Graphic Tee",
    "description": "A great vintage band tee with faded print.",
    "category": "tops",
    "style_tags": ["vintage", "graphic tee", "streetwear"],
    "size": "M",
    "condition": "good",
    "price": 22.00,
    "colors": ["black", "white"],
    "brand": "Levi's",
    "platform": "depop",
}


class TestHandleQuery:
    def test_empty_query_returns_validation_message(self):
        listing, outfit, fit_card = app.handle_query("   ", "Example wardrobe")

        assert listing == "Please enter a search query."
        assert outfit == ""
        assert fit_card == ""

    def test_error_session_returns_first_panel_only(self, monkeypatch):
        monkeypatch.setattr(app, "get_example_wardrobe", lambda: {"items": []})
        monkeypatch.setattr(
            app,
            "run_agent",
            lambda query, wardrobe: {
                "error": "No listings found.",
                "notes": ["Removed price filter and retried."],
            },
        )

        listing, outfit, fit_card = app.handle_query("designer ballgown", "Example wardrobe")

        assert "Removed price filter and retried." in listing
        assert "No listings found." in listing
        assert outfit == ""
        assert fit_card == ""

    def test_success_formats_listing_and_returns_all_outputs(self, monkeypatch):
        monkeypatch.setattr(app, "get_example_wardrobe", lambda: {"items": [{"name": "Jeans"}]})
        monkeypatch.setattr(
            app,
            "run_agent",
            lambda query, wardrobe: {
                "error": None,
                "notes": ["Removed price filter and retried."],
                "selected_item": SAMPLE_ITEM,
                "outfit_suggestion": "Pair it with loose jeans and sneakers.",
                "fit_card": "Found this on depop and built the easiest weekend look.",
            },
        )

        listing, outfit, fit_card = app.handle_query(
            "vintage graphic tee under $30",
            "Example wardrobe",
        )

        assert "Removed price filter and retried." in listing
        assert "Vintage Graphic Tee" in listing
        assert "Price: $22.00" in listing
        assert "Platform: depop" in listing
        assert "Brand: Levi's" in listing
        assert "A great vintage band tee with faded print." in listing
        assert outfit == "Pair it with loose jeans and sneakers."
        assert fit_card == "Found this on depop and built the easiest weekend look."

    def test_empty_wardrobe_option_uses_empty_loader(self, monkeypatch):
        empty_called = {"count": 0}

        def fake_empty():
            empty_called["count"] += 1
            return {"items": []}

        monkeypatch.setattr(app, "get_empty_wardrobe", fake_empty)
        monkeypatch.setattr(
            app,
            "run_agent",
            lambda query, wardrobe: {
                "error": None,
                "notes": [],
                "selected_item": SAMPLE_ITEM,
                "outfit_suggestion": "General styling advice",
                "fit_card": "Simple fit card",
            },
        )

        app.handle_query("vintage graphic tee", "Empty wardrobe (new user)")

        assert empty_called["count"] == 1
