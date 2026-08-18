"""Unit tests for the shared helpers in vainu_cli.common."""

import pytest

from vainu_cli.common import COUNT_PENDING_STATUSES, count_is_pending, count_payload


class TestCountIsPending:
    @pytest.mark.parametrize("status", sorted(COUNT_PENDING_STATUSES))
    def test_pending_statuses_keep_polling(self, status):
        assert count_is_pending({"count": None, "status": status}) is True

    @pytest.mark.parametrize("status", ["ready", "error"])
    def test_terminal_statuses_stop_polling(self, status):
        assert count_is_pending({"count": 12300, "status": status}) is False

    def test_unknown_status_stops_polling(self):
        """Better to hand back a surprise than to spin until the timeout."""
        assert count_is_pending({"status": "something-new"}) is False

    def test_body_without_a_status_stops_polling(self):
        """A rejected payload comes back as a 400 body carrying no `status` key."""
        assert count_is_pending({"detail": "No database permission"}) is False
        assert count_is_pending({}) is False

    @pytest.mark.parametrize("response", [None, "scheduled", 42, ["scheduled"]])
    def test_non_dict_responses_stop_polling(self, response):
        assert count_is_pending(response) is False


class TestCountPayload:
    SEARCH_PAYLOAD = {
        "query": {"?GTE": {"financial_data.revenue": 100000000}},
        "database": "FI",
        "order": "-financial_data.revenue",
        "fields": ["name", "business_id"],
        "limit": 50,
        "offset": 10,
    }

    def test_order_is_dropped(self):
        """The count endpoint 400s on any `order` value, so it must never be sent."""
        assert "order" not in count_payload(self.SEARCH_PAYLOAD)

    def test_order_is_dropped_from_follow_up_polls_too(self):
        assert "order" not in count_payload(self.SEARCH_PAYLOAD, first_request=False)

    def test_query_and_database_survive(self):
        result = count_payload(self.SEARCH_PAYLOAD)
        assert result["query"] == self.SEARCH_PAYLOAD["query"]
        assert result["database"] == "FI"

    def test_ignored_but_accepted_keys_are_left_alone(self):
        """fields/limit/offset are documented as ignored and cause no error."""
        result = count_payload(self.SEARCH_PAYLOAD)
        assert result["fields"] == ["name", "business_id"]
        assert result["limit"] == 50
        assert result["offset"] == 10

    def test_recount_rides_on_the_first_request_only(self):
        payload = {"list": "abc", "recount": True, "recount_if_cache_max_age": 3600}
        assert count_payload(payload, first_request=True)["recount"] is True
        follow_up = count_payload(payload, first_request=False)
        assert "recount" not in follow_up
        assert follow_up["recount_if_cache_max_age"] == 3600

    def test_caller_payload_is_not_mutated(self):
        payload = dict(self.SEARCH_PAYLOAD)
        count_payload(payload, first_request=False)
        assert payload == self.SEARCH_PAYLOAD

    def test_payload_without_stripped_keys_is_unchanged(self):
        payload = {"list": "abc", "async": False}
        assert count_payload(payload) == payload
