"""
tests/test_tools.py

Pytest tests for all three FitFindr tools.
Run from the project root:  pytest tests/test_tools.py -v

Coverage:
  - search_listings: filtering, keyword scoring, edge/failure cases
  - suggest_outfit:  empty wardrobe path, populated wardrobe path, missing key
  - create_fit_card: valid input, empty outfit (failure modes), whitespace outfit
"""

import os
import sys
import types

import pytest

# Make sure the project root is on the path so imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tools  # noqa: E402 — must come after sys.path fixup


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

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

SAMPLE_WARDROBE_WITH_ITEMS = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue"],
            "style_tags": ["denim", "streetwear"],
            "notes": None,
        },
        {
            "id": "w_002",
            "name": "White ribbed tank top",
            "category": "tops",
            "colors": ["white"],
            "style_tags": ["basics", "minimal"],
            "notes": None,
        },
    ]
}

EMPTY_WARDROBE = {"items": []}


def _mock_groq_client(monkeypatch, return_text: str):
    """
    Replace _get_groq_client() with a stub that returns `return_text`
    from chat.completions.create(), without hitting the real API.
    """
    fake_message = types.SimpleNamespace(content=return_text)
    fake_choice = types.SimpleNamespace(message=fake_message)
    fake_response = types.SimpleNamespace(choices=[fake_choice])

    class FakeCompletions:
        def create(self, **kwargs):
            return fake_response

    class FakeChat:
        completions = FakeCompletions()

    class FakeGroq:
        chat = FakeChat()

    monkeypatch.setattr(tools, "_get_groq_client", lambda: FakeGroq())


# ─────────────────────────────────────────────────────────────────────────────
# Tool 1: search_listings
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchListings:

    # --- Success cases -------------------------------------------------------

    def test_returns_results_for_matching_description(self):
        results = tools.search_listings("vintage jeans denim")
        assert len(results) > 0, "Expected at least one match for 'vintage jeans denim'"

    def test_results_are_dicts_with_required_fields(self):
        results = tools.search_listings("vintage")
        required = {"id", "title", "description", "category", "style_tags",
                    "size", "condition", "price", "colors", "brand", "platform"}
        for item in results:
            assert required.issubset(item.keys()), f"Listing missing fields: {item}"

    def test_price_filter_excludes_expensive_items(self):
        results = tools.search_listings("vintage", max_price=20.0)
        for item in results:
            assert item["price"] <= 20.0, f"Item ${item['price']} exceeds max_price=20"

    def test_size_filter_case_insensitive(self):
        # "m" should match listings with size "M", "S/M", etc.
        results = tools.search_listings("shirt", size="m")
        for item in results:
            assert "m" in item["size"].lower(), (
                f"Size '{item['size']}' did not match filter 'm'"
            )

    def test_both_filters_applied_together(self):
        results = tools.search_listings("vintage", size="M", max_price=30.0)
        for item in results:
            assert item["price"] <= 30.0
            assert "m" in item["size"].lower()

    def test_higher_keyword_overlap_ranks_first(self):
        # A listing matching 3 of our keywords should outscore one matching 1.
        # Use keywords that map to real listings: "vintage graphic tee streetwear"
        results = tools.search_listings("vintage graphic tee streetwear")
        assert len(results) >= 2
        # The top result should be a top/tee, not something completely unrelated
        top = results[0]
        combined = (top["title"] + " " + " ".join(top["style_tags"])).lower()
        assert any(kw in combined for kw in ["graphic", "tee", "vintage", "streetwear"])

    def test_no_size_or_price_filter_returns_broad_results(self):
        results = tools.search_listings("vintage")
        assert len(results) > 5, "Expected many vintage items without filters"

    def test_returns_list_type(self):
        results = tools.search_listings("denim jacket")
        assert isinstance(results, list)

    # --- Failure / edge cases ------------------------------------------------

    def test_no_matches_returns_empty_list_not_exception(self):
        # A completely nonsensical description should return [] without raising.
        results = tools.search_listings("xyzzy_nonexistent_item_qqqq")
        assert results == [], f"Expected empty list, got {results}"

    def test_empty_description_returns_empty_list(self):
        # No tokens means no overlap → every score is 0 → all dropped.
        results = tools.search_listings("")
        assert results == []

    def test_price_filter_zero_returns_empty_list(self):
        results = tools.search_listings("vintage", max_price=0.0)
        assert results == []

    def test_impossible_size_returns_empty_list(self):
        results = tools.search_listings("vintage", size="XXXXXXXXL")
        assert results == []

    def test_does_not_raise_on_no_results(self):
        # Explicitly confirm no exception is raised (not just empty).
        try:
            tools.search_listings("asdfghjklqwerty", max_price=0.01, size="XXXXXXXXL")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"search_listings raised unexpectedly: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2: suggest_outfit
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestOutfit:

    # --- Success cases -------------------------------------------------------

    def test_returns_nonempty_string_with_wardrobe(self, monkeypatch):
        _mock_groq_client(monkeypatch, "Outfit 1: pair with baggy jeans.")
        result = tools.suggest_outfit(SAMPLE_ITEM, SAMPLE_WARDROBE_WITH_ITEMS)
        assert isinstance(result, str)
        assert result.strip() != ""

    def test_returns_nonempty_string_with_empty_wardrobe(self, monkeypatch):
        _mock_groq_client(monkeypatch, "Try this with straight-leg trousers and sneakers.")
        result = tools.suggest_outfit(SAMPLE_ITEM, EMPTY_WARDROBE)
        assert isinstance(result, str)
        assert result.strip() != ""

    def test_llm_response_is_passed_through(self, monkeypatch):
        expected = "Rock it with baggy jeans and chunky sneakers for that 90s vibe."
        _mock_groq_client(monkeypatch, expected)
        result = tools.suggest_outfit(SAMPLE_ITEM, SAMPLE_WARDROBE_WITH_ITEMS)
        assert result == expected

    def test_empty_wardrobe_still_calls_llm(self, monkeypatch):
        """Empty wardrobe must trigger a real LLM call (general advice), not a silent empty return."""
        called = {"count": 0}
        original = tools._get_groq_client

        def tracking_client():
            called["count"] += 1
            return original()  # still replaced by _mock_groq_client below

        _mock_groq_client(monkeypatch, "General styling advice here.")
        # Override again to also count calls
        real_fake = tools._get_groq_client

        def counting_fake():
            called["count"] += 1
            return real_fake()

        monkeypatch.setattr(tools, "_get_groq_client", counting_fake)

        tools.suggest_outfit(SAMPLE_ITEM, EMPTY_WARDROBE)
        assert called["count"] == 1, "Expected exactly one LLM call for empty wardrobe"

    def test_wardrobe_missing_items_key_treated_as_empty(self, monkeypatch):
        """A wardrobe dict without 'items' should not raise — treat as empty."""
        _mock_groq_client(monkeypatch, "General advice since no wardrobe provided.")
        result = tools.suggest_outfit(SAMPLE_ITEM, {})
        assert isinstance(result, str)
        assert result.strip() != ""

    # --- Failure / edge cases ------------------------------------------------

    def test_missing_api_key_raises_value_error(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            tools.suggest_outfit(SAMPLE_ITEM, SAMPLE_WARDROBE_WITH_ITEMS)


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3: create_fit_card
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateFitCard:

    VALID_OUTFIT = (
        "Outfit 1: Vintage Graphic Tee tucked into baggy dark-wash jeans "
        "with white sneakers — effortless 90s streetwear energy."
    )

    # --- Success cases -------------------------------------------------------

    def test_returns_nonempty_string_for_valid_input(self, monkeypatch):
        _mock_groq_client(monkeypatch, "Thrifted this gem on depop for $22 and I'm obsessed.")
        result = tools.create_fit_card(self.VALID_OUTFIT, SAMPLE_ITEM)
        assert isinstance(result, str)
        assert result.strip() != ""

    def test_llm_response_passed_through(self, monkeypatch):
        expected = "Found this Vintage Graphic Tee on depop for $22 and living for it."
        _mock_groq_client(monkeypatch, expected)
        result = tools.create_fit_card(self.VALID_OUTFIT, SAMPLE_ITEM)
        assert result == expected

    def test_uses_higher_temperature(self, monkeypatch):
        """Verify create() is called with temperature >= 0.9."""
        temperatures_used = []

        fake_message = types.SimpleNamespace(content="caption text")
        fake_choice = types.SimpleNamespace(message=fake_message)
        fake_response = types.SimpleNamespace(choices=[fake_choice])

        class TrackingCompletions:
            def create(self, **kwargs):
                temperatures_used.append(kwargs.get("temperature", 0))
                return fake_response

        class FakeChat:
            completions = TrackingCompletions()

        class FakeGroq:
            chat = FakeChat()

        monkeypatch.setattr(tools, "_get_groq_client", lambda: FakeGroq())
        tools.create_fit_card(self.VALID_OUTFIT, SAMPLE_ITEM)
        assert temperatures_used[0] >= 0.9, (
            f"Expected temperature >= 0.9 for creative variety, got {temperatures_used[0]}"
        )

    # --- Failure modes — empty/missing outfit --------------------------------

    def test_empty_outfit_returns_error_string_not_exception(self):
        result = tools.create_fit_card("", SAMPLE_ITEM)
        assert isinstance(result, str)
        assert result.strip() != ""
        assert "error" in result.lower() or "missing" in result.lower() or "empty" in result.lower()

    def test_whitespace_only_outfit_returns_error_string(self):
        result = tools.create_fit_card("   \t\n  ", SAMPLE_ITEM)
        assert isinstance(result, str)
        assert "error" in result.lower() or "missing" in result.lower() or "empty" in result.lower()

    def test_empty_outfit_does_not_raise(self):
        try:
            tools.create_fit_card("", SAMPLE_ITEM)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"create_fit_card raised unexpectedly on empty outfit: {exc}")

    def test_whitespace_outfit_does_not_call_llm(self, monkeypatch):
        """An empty/whitespace outfit must short-circuit before touching the LLM."""
        called = {"count": 0}

        def fail_client():
            called["count"] += 1
            raise RuntimeError("LLM should not be called for empty outfit")

        monkeypatch.setattr(tools, "_get_groq_client", fail_client)
        result = tools.create_fit_card("   ", SAMPLE_ITEM)
        assert called["count"] == 0, "LLM was called despite empty outfit"
        assert isinstance(result, str)

    def test_missing_api_key_raises_value_error_for_valid_outfit(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            tools.create_fit_card(self.VALID_OUTFIT, SAMPLE_ITEM)
