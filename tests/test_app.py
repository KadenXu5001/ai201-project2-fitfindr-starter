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


def _collect_outputs(generator):
    return list(generator)


def _step(session, step=1, action="suggest_outfit", explanation="Generated styling advice.", observation="Generated outfit suggestion."):
    return {
        "step": step,
        "action": action,
        "source": "deterministic",
        "reason": "",
        "explanation": explanation,
        "observation": observation,
        "session": session,
    }


class TestHandleQuery:
    def test_empty_query_returns_validation_message(self):
        outputs = _collect_outputs(app.handle_query("   ", "Example wardrobe"))

        assert outputs == [("Please enter a search query.", "", "", "", {})]

    def test_error_session_returns_first_panel_only(self, monkeypatch):
        monkeypatch.setattr(app, "get_example_wardrobe", lambda: {"items": []})

        session = {
            "query": "designer ballgown",
            "current_constraints": {"description": "designer ballgown", "size": None, "max_price": None},
            "relaxations": {"price": True, "size": False},
            "search_status": "no_results",
            "search_attempts": [],
            "selected_item": None,
            "tool_history": [{"action": "fail_no_results", "observation": "No listings found."}],
            "notes": ["Removed price filter and retried."],
            "error": "No listings found.",
        }
        monkeypatch.setattr(app, "iter_agent", lambda query, wardrobe, listings=None: iter([_step(session, action="fail_no_results", explanation="No results after retries.", observation="No listings found.")]))

        outputs = _collect_outputs(app.handle_query("designer ballgown", "Example wardrobe"))
        listing, outfit, fit_card, dashboard, session_state = outputs[-1]

        assert "Removed price filter and retried." in listing
        assert "No listings found." in listing
        assert outfit == ""
        assert fit_card == ""
        assert "selected fail_no_results tool" in dashboard
        assert session_state["search_status"] == "no_results"

    def test_success_formats_listing_and_returns_all_outputs(self, monkeypatch):
        monkeypatch.setattr(app, "get_example_wardrobe", lambda: {"items": [{"name": "Jeans"}]})

        session = {
            "query": "vintage graphic tee under $30",
            "current_constraints": {"description": "vintage graphic tee", "size": None, "max_price": 30.0},
            "relaxations": {"price": True, "size": False},
            "search_status": "results_found",
            "search_attempts": [
                {"description": "vintage graphic tee", "size": None, "max_price": 30.0, "result_count": 1}
            ],
            "selected_item": SAMPLE_ITEM,
            "tool_history": [{"action": "create_fit_card", "observation": "Created fit card."}],
            "notes": ["Removed price filter and retried."],
            "error": None,
            "outfit_suggestion": "Pair it with loose jeans and sneakers.",
            "fit_card": "Found this on depop and built the easiest weekend look.",
        }
        monkeypatch.setattr(app, "iter_agent", lambda query, wardrobe, listings=None: iter([_step(session, action="create_fit_card", explanation="Created the fit card.", observation="Created fit card.")]))

        outputs = _collect_outputs(app.handle_query("vintage graphic tee under $30", "Example wardrobe"))
        listing, outfit, fit_card, dashboard, session_state = outputs[-1]

        assert "Removed price filter and retried." in listing
        assert "Vintage Graphic Tee" in listing
        assert "Price: $22.00" in listing
        assert "Platform: depop" in listing
        assert "Brand: Levi's" in listing
        assert "A great vintage band tee with faded print." in listing
        assert outfit == "Pair it with loose jeans and sneakers."
        assert fit_card == "Found this on depop and built the easiest weekend look."
        assert "selected create_fit_card tool" in dashboard
        assert session_state["selected_item"] == "Vintage Graphic Tee"

    def test_empty_wardrobe_option_uses_empty_loader(self, monkeypatch):
        empty_called = {"count": 0}
        captured = {}

        def fake_empty():
            empty_called["count"] += 1
            return {"items": []}

        def fake_iter_agent(query, wardrobe, listings=None):
            captured["wardrobe"] = wardrobe
            session = {
                "query": query,
                "current_constraints": {"description": "vintage graphic tee", "size": None, "max_price": None},
                "relaxations": {"price": False, "size": False},
                "search_status": "results_found",
                "search_attempts": [],
                "selected_item": SAMPLE_ITEM,
                "tool_history": [{"action": "suggest_outfit", "observation": "Generated outfit suggestion."}],
                "notes": [],
                "error": None,
                "outfit_suggestion": "General styling advice",
                "fit_card": "Simple fit card",
            }
            return iter([_step(session)])

        monkeypatch.setattr(app, "get_empty_wardrobe", fake_empty)
        monkeypatch.setattr(app, "iter_agent", fake_iter_agent)

        outputs = _collect_outputs(app.handle_query("vintage graphic tee", "Empty wardrobe (new user)"))
        listing, outfit, fit_card, dashboard, session_state = outputs[-1]

        assert empty_called["count"] == 1
        assert captured["wardrobe"] == {"items": []}
        assert "Vintage Graphic Tee" in listing
        assert outfit == "General styling advice"
        assert fit_card == "Simple fit card"
        assert "selected suggest_outfit tool" in dashboard
        assert session_state["selected_item"] == "Vintage Graphic Tee"
