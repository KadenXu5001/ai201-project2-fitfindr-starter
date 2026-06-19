import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent  # noqa: E402


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
    "brand": None,
    "platform": "depop",
}

SECOND_ITEM = {
    "id": "lst_alt",
    "title": "Vintage Graphic Tee in Blue",
    "description": "Vintage tee with washed blue cotton and oversized fit.",
    "category": "tops",
    "style_tags": ["vintage", "graphic tee", "streetwear", "denim"],
    "size": "M",
    "condition": "good",
    "price": 18.00,
    "colors": ["blue", "white"],
    "brand": None,
    "platform": "depop",
}

SAMPLE_WARDROBE = {
    "items": [
        {
            "name": "Baggy jeans",
            "category": "bottoms",
            "colors": ["blue"],
            "style_tags": ["denim", "streetwear"],
        }
    ]
}


@pytest.fixture(autouse=True)
def stub_planner(monkeypatch):
    monkeypatch.setattr(
        agent,
        "_query_planner_decision",
        lambda session, valid_actions: (
            valid_actions[0],
            "Test planner picked the first valid action.",
            '{"action": "stub"}',
        ),
    )


class TestParseQuery:
    def test_extracts_description_size_and_price(self):
        parsed = agent._parse_query("vintage graphic tee under $30, size M")

        assert parsed == {
            "description": "vintage graphic tee",
            "size": "M",
            "max_price": 30.0,
        }

    def test_handles_query_without_filters(self):
        parsed = agent._parse_query("black combat boots")

        assert parsed == {
            "description": "black combat boots",
            "size": None,
            "max_price": None,
        }


class TestRunAgent:
    def test_happy_path_populates_session(self, monkeypatch):
        monkeypatch.setattr(
            agent,
            "search_listings",
            lambda description, size=None, max_price=None: [SAMPLE_ITEM],
        )
        monkeypatch.setattr(
            agent,
            "suggest_outfit",
            lambda new_item, wardrobe: "Pair it with baggy jeans and sneakers.",
        )
        monkeypatch.setattr(
            agent,
            "create_fit_card",
            lambda outfit, new_item: "Found the perfect vintage tee fit.",
        )

        session = agent.run_agent("vintage graphic tee under $30, size M", SAMPLE_WARDROBE)

        assert session["error"] is None
        assert session["parsed"]["description"] == "vintage graphic tee"
        assert session["parsed"]["size"] == "M"
        assert session["parsed"]["max_price"] == 30.0
        assert session["search_results"] == [SAMPLE_ITEM]
        assert session["selected_item"] == SAMPLE_ITEM
        assert session["outfit_suggestion"] == "Pair it with baggy jeans and sneakers."
        assert session["fit_card"] == "Found the perfect vintage tee fit."
        assert session["notes"] == []
        assert [step["action"] for step in session["tool_history"]] == [
            "parse_query",
            "search_listings",
            "select_item",
            "suggest_outfit",
            "create_fit_card",
        ]

    def test_relaxes_price_then_succeeds(self, monkeypatch):
        calls = []

        def fake_search(description, size=None, max_price=None):
            calls.append((description, size, max_price))
            if max_price is not None:
                return []
            return [SAMPLE_ITEM]

        monkeypatch.setattr(agent, "search_listings", fake_search)
        monkeypatch.setattr(agent, "suggest_outfit", lambda *_: "Outfit idea")
        monkeypatch.setattr(agent, "create_fit_card", lambda *_: "Fit card")

        session = agent.run_agent("vintage graphic tee under $30, size M", SAMPLE_WARDROBE)

        assert calls == [
            ("vintage graphic tee", "M", 30.0),
            ("vintage graphic tee", "M", None),
        ]
        assert session["error"] is None
        assert len(session["notes"]) == 1
        assert "price filter" in session["notes"][0].lower()
        assert [step["action"] for step in session["tool_history"]] == [
            "parse_query",
            "search_listings",
            "relax_price",
            "search_listings",
            "select_item",
            "suggest_outfit",
            "create_fit_card",
        ]
        assert session["planner_history"][2]["source"] == "llm"
        assert session["planner_history"][2]["action"] == "relax_price"

    def test_relaxes_price_and_size_before_failing(self, monkeypatch):
        calls = []

        def fake_search(description, size=None, max_price=None):
            calls.append((description, size, max_price))
            return []

        downstream_calls = {"suggest": 0, "card": 0}

        monkeypatch.setattr(agent, "search_listings", fake_search)
        monkeypatch.setattr(
            agent,
            "suggest_outfit",
            lambda *_: downstream_calls.__setitem__("suggest", downstream_calls["suggest"] + 1),
        )
        monkeypatch.setattr(
            agent,
            "create_fit_card",
            lambda *_: downstream_calls.__setitem__("card", downstream_calls["card"] + 1),
        )

        session = agent.run_agent("designer ballgown size XXS under $5", SAMPLE_WARDROBE)

        assert calls == [
            ("designer ballgown", "XXS", 5.0),
            ("designer ballgown", "XXS", None),
            ("designer ballgown", None, None),
        ]
        assert session["selected_item"] is None
        assert session["outfit_suggestion"] is None
        assert session["fit_card"] is None
        assert "No listings found" in session["error"]
        assert len(session["notes"]) == 2
        assert downstream_calls == {"suggest": 0, "card": 0}

    def test_no_filters_and_no_results_returns_error(self, monkeypatch):
        monkeypatch.setattr(agent, "search_listings", lambda *args, **kwargs: [])

        session = agent.run_agent("totally made up item", SAMPLE_WARDROBE)

        assert session["parsed"] == {
            "description": "totally made up item",
            "size": None,
            "max_price": None,
        }
        assert session["notes"] == []
        assert session["error"] is not None

    def test_selects_item_based_on_wardrobe_compatibility(self, monkeypatch):
        monkeypatch.setattr(
            agent,
            "search_listings",
            lambda description, size=None, max_price=None: [SAMPLE_ITEM, SECOND_ITEM],
        )
        monkeypatch.setattr(agent, "suggest_outfit", lambda new_item, wardrobe: new_item["title"])
        monkeypatch.setattr(
            agent,
            "create_fit_card",
            lambda outfit, new_item: f"Caption for {new_item['title']}",
        )

        session = agent.run_agent("vintage graphic tee", SAMPLE_WARDROBE)

        assert session["selected_item"] == SECOND_ITEM
        assert session["outfit_suggestion"] == "Vintage Graphic Tee in Blue"
        assert session["fit_card"] == "Caption for Vintage Graphic Tee in Blue"

    def test_create_fit_card_error_is_promoted_to_session_error(self, monkeypatch):
        monkeypatch.setattr(
            agent,
            "search_listings",
            lambda description, size=None, max_price=None: [SAMPLE_ITEM],
        )
        monkeypatch.setattr(agent, "suggest_outfit", lambda *_: "Outfit idea")
        monkeypatch.setattr(
            agent,
            "create_fit_card",
            lambda *_: "Error: Cannot generate a fit card.",
        )

        session = agent.run_agent("vintage graphic tee", SAMPLE_WARDROBE)

        assert session["fit_card"] is None
        assert session["error"] == "Error: Cannot generate a fit card."

    def test_empty_wardrobe_still_generates_general_styling_and_fit_card(self, monkeypatch):
        empty_wardrobe = {"items": []}

        monkeypatch.setattr(
            agent,
            "search_listings",
            lambda description, size=None, max_price=None: [SAMPLE_ITEM],
        )
        monkeypatch.setattr(
            agent,
            "suggest_outfit",
            lambda new_item, wardrobe: (
                "Try it with straight-leg jeans, a white tank, and simple sneakers."
                if wardrobe == empty_wardrobe else ""
            ),
        )
        monkeypatch.setattr(
            agent,
            "create_fit_card",
            lambda outfit, new_item: "Easy thrift win for a casual weekend look.",
        )

        session = agent.run_agent("vintage graphic tee", empty_wardrobe)

        assert session["error"] is None
        assert session["selected_item"] == SAMPLE_ITEM
        assert "straight-leg jeans" in session["outfit_suggestion"]
        assert session["fit_card"] == "Easy thrift win for a casual weekend look."

    def test_planner_can_choose_size_relaxation_first(self, monkeypatch):
        def fake_search(description, size=None, max_price=None):
            if size == "M":
                return []
            return [SAMPLE_ITEM]

        def fake_planner(session, valid_actions):
            if "relax_size" in valid_actions:
                return (
                    "relax_size",
                    "The size filter seems too narrow for this request.",
                    '{"action":"relax_size","reason":"size seems over-constraining"}',
                )
            return (
                valid_actions[0],
                "Only one action was available.",
                '{"action":"fallback"}',
            )

        monkeypatch.setattr(agent, "search_listings", fake_search)
        monkeypatch.setattr(agent, "suggest_outfit", lambda *_: "Outfit idea")
        monkeypatch.setattr(agent, "create_fit_card", lambda *_: "Fit card")
        monkeypatch.setattr(agent, "_query_planner_decision", fake_planner)

        session = agent.run_agent("vintage graphic tee under $30, size M", SAMPLE_WARDROBE)

        assert session["error"] is None
        assert session["search_attempts"] == [
            {
                "description": "vintage graphic tee",
                "size": "M",
                "max_price": 30.0,
                "result_count": 0,
            },
            {
                "description": "vintage graphic tee",
                "size": None,
                "max_price": 30.0,
                "result_count": 1,
            },
        ]
        assert "size filter" in session["notes"][0].lower()
        assert session["planner_history"][2]["action"] == "relax_size"

    def test_invalid_planner_output_falls_back_safely(self, monkeypatch):
        calls = []

        def fake_search(description, size=None, max_price=None):
            calls.append((description, size, max_price))
            if max_price is not None:
                return []
            return [SAMPLE_ITEM]

        monkeypatch.setattr(agent, "search_listings", fake_search)
        monkeypatch.setattr(agent, "suggest_outfit", lambda *_: "Outfit idea")
        monkeypatch.setattr(agent, "create_fit_card", lambda *_: "Fit card")
        monkeypatch.setattr(
            agent,
            "_query_planner_decision",
            lambda session, valid_actions: (_ for _ in ()).throw(ValueError("bad planner output")),
        )

        session = agent.run_agent("vintage graphic tee under $30, size M", SAMPLE_WARDROBE)

        assert session["error"] is None
        assert calls == [
            ("vintage graphic tee", "M", 30.0),
            ("vintage graphic tee", "M", None),
        ]
        assert session["planner_history"][2]["source"] == "fallback"
        assert session["planner_history"][2]["action"] == "relax_price"


class TestValidActions:
    def test_selected_item_requires_suggest_outfit_before_finish(self):
        session = agent._new_session("vintage graphic tee", SAMPLE_WARDROBE)
        session["parsed"] = {"description": "vintage graphic tee", "size": None, "max_price": None}
        session["current_constraints"] = session["parsed"].copy()
        session["search_status"] = "results_found"
        session["search_results"] = [SAMPLE_ITEM]
        session["selected_item"] = SAMPLE_ITEM

        assert agent._valid_actions_for_state(session) == ["suggest_outfit"]

    def test_outfit_requires_fit_card_before_finish(self):
        session = agent._new_session("vintage graphic tee", SAMPLE_WARDROBE)
        session["parsed"] = {"description": "vintage graphic tee", "size": None, "max_price": None}
        session["current_constraints"] = session["parsed"].copy()
        session["search_status"] = "results_found"
        session["search_results"] = [SAMPLE_ITEM]
        session["selected_item"] = SAMPLE_ITEM
        session["outfit_suggestion"] = "Pair it with baggy jeans and sneakers."

        assert agent._valid_actions_for_state(session) == ["create_fit_card"]
