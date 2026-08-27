"""Unit tests for the shared helpers in vainu_cli.common."""

import logging

import pytest

from vainu_cli.common import (
    COUNT_PENDING_STATUSES,
    DEFAULT_ASYNC_MAX_WAIT_SECONDS,
    POLL_RETRY_MAX_BACKOFF_SECONDS,
    LineDecoder,
    companies_request,
    count_is_pending,
    count_payload,
    is_line_safe,
    poll_retry_delay,
    requested_encoding,
    response_encoding,
    with_encoding,
)


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


class TestPollRetryDelay:
    def test_first_retry_waits_one_poll_interval(self):
        assert poll_retry_delay(3, 1) == 3

    def test_delay_doubles_per_consecutive_failure(self):
        assert [poll_retry_delay(3, n) for n in range(1, 5)] == [3, 6, 12, 24]

    def test_delay_is_capped(self):
        assert poll_retry_delay(3, 20) == POLL_RETRY_MAX_BACKOFF_SECONDS

    def test_zero_interval_never_sleeps(self):
        """Tests drive the poll loops with interval 0 — backoff must stay 0."""
        assert poll_retry_delay(0, 4) == 0


class TestAsyncMaxWait:
    def test_both_clients_share_the_same_cap(self):
        """The two clients used to drift — 4 hours sync, unbounded async."""
        from vainu_cli._async_client import VainuAPIBaseClient as AsyncBase
        from vainu_cli._sync_client import VainuAPIBaseClient as SyncBase

        assert AsyncBase.ASYNC_MAX_WAIT_SECONDS == DEFAULT_ASYNC_MAX_WAIT_SECONDS
        assert SyncBase.ASYNC_MAX_WAIT_SECONDS == DEFAULT_ASYNC_MAX_WAIT_SECONDS


class TestWithEncoding:
    PAYLOAD = {"database": "FI", "fields": ["name"]}

    def test_csv_payload_asks_for_utf8(self):
        """Without this the API renders CSV as ISO-8859-1 — see the module comment."""
        assert with_encoding(self.PAYLOAD, "csv") == {**self.PAYLOAD, "encoding": "utf-8"}

    def test_original_payload_is_left_alone(self):
        with_encoding(self.PAYLOAD, "csv")
        assert "encoding" not in self.PAYLOAD

    @pytest.mark.parametrize("format", ["json", "jsonl"])
    def test_json_formats_are_untouched(self, format):
        """Both JSON renderers answer in UTF-8 whatever the payload says."""
        assert with_encoding(self.PAYLOAD, format) == self.PAYLOAD

    def test_caller_chosen_encoding_wins(self):
        payload = {**self.PAYLOAD, "encoding": "latin-1"}
        assert with_encoding(payload, "csv") == payload

    def test_query_string_payload_gets_the_parameter(self):
        assert with_encoding("?country=FI", "csv") == "?country=FI&encoding=utf-8"

    @pytest.mark.parametrize("payload", ["?", "?country=FI&"])
    def test_query_string_payload_does_not_double_the_separator(self, payload):
        assert with_encoding(payload, "csv") == f"{payload}encoding=utf-8"

    def test_query_string_encoding_is_kept(self):
        assert (
            with_encoding("?country=FI&encoding=latin-1", "csv") == "?country=FI&encoding=latin-1"
        )

    def test_empty_encoding_is_replaced(self):
        """An empty value is not a choice — the API falls back to its legacy codec."""
        assert with_encoding({"encoding": ""}, "csv") == {"encoding": "utf-8"}

    def test_an_explicit_encoding_overrides_the_payload(self):
        """A --encoding flag has to beat an `encoding` saved in a payload file."""
        payload = {**self.PAYLOAD, "encoding": "utf-8"}
        assert with_encoding(payload, "csv", "latin-1") == {**self.PAYLOAD, "encoding": "latin-1"}

    def test_an_explicit_encoding_is_added_to_a_query_string(self):
        assert with_encoding("?country=FI", "csv", "latin-1") == "?country=FI&encoding=latin-1"

    def test_an_explicit_encoding_replaces_the_one_in_a_query_string(self):
        assert (
            with_encoding("?country=FI&encoding=utf-8&limit=5", "csv", "latin-1")
            == "?country=FI&encoding=latin-1&limit=5"
        )

    @pytest.mark.parametrize("format", ["json", "jsonl"])
    def test_json_formats_ignore_an_explicit_encoding(self, format):
        assert with_encoding(self.PAYLOAD, format, "latin-1") == self.PAYLOAD


class TestRequestedEncoding:
    def test_reads_a_dict_payload(self):
        assert requested_encoding({"encoding": "utf-16"}) == "utf-16"

    def test_reads_a_query_string_payload(self):
        assert requested_encoding("?country=FI&encoding=utf-16") == "utf-16"

    @pytest.mark.parametrize("payload", [{}, {"encoding": ""}, "?country=FI", "?encoding="])
    def test_absent_or_empty_reads_as_unset(self, payload):
        assert requested_encoding(payload) is None


class TestResponseEncoding:
    def test_csv_follows_the_payload(self):
        assert response_encoding({"encoding": "latin-1"}, "csv") == "latin-1"

    def test_csv_defaults_to_utf8(self):
        assert response_encoding({}, "csv") == "utf-8"

    @pytest.mark.parametrize("format", ["json", "jsonl"])
    def test_json_formats_stay_utf8(self, format):
        """The JSON renderers ignore `encoding`, and one payload is reused across formats."""
        assert response_encoding({"encoding": "latin-1"}, format) == "utf-8"


class TestCompaniesRequestEncoding:
    def test_csv_post_body_carries_the_encoding(self):
        _, _, body = companies_request({"country": "FI"}, "csv")
        assert body == {"country": "FI", "encoding": "utf-8"}

    def test_csv_get_query_carries_the_encoding(self):
        _, path, body = companies_request("?country=FI", "csv")
        assert path == "/v2/companies/?country=FI&encoding=utf-8&format=csv"
        assert body is None

    def test_jsonl_request_is_unchanged(self):
        _, path, body = companies_request({"country": "FI"}, "jsonl")
        assert body == {"country": "FI"}
        assert path == "/v2/companies/?format=jsonl"


class TestLineDecoder:
    def test_decodes_the_requested_encoding(self):
        assert LineDecoder()("Tynjälä".encode()) == "Tynjälä"

    def test_decodes_a_caller_chosen_encoding(self):
        assert LineDecoder("latin-1")("Tynjälä".encode("latin-1")) == "Tynjälä"

    def test_a_mismatched_body_falls_back_instead_of_raising(self):
        """A strict decode would abort the export mid-row, after earlier rows shipped."""
        assert LineDecoder()("Tynjälä".encode("latin-1")) == "Tynjälä"

    def test_undecodable_bytes_are_replaced(self):
        assert LineDecoder()(b"\x81") == "\ufffd"

    def test_the_fallback_is_logged_once_per_body(self, caplog):
        decode = LineDecoder()
        with caplog.at_level(logging.WARNING, logger="vainu_cli.common"):
            for _ in range(3):
                decode("Tynjälä".encode("latin-1"))
        assert len(caplog.records) == 1
        assert "utf-8" in caplog.records[0].getMessage()


class TestIsLineSafe:
    @pytest.mark.parametrize("encoding", ["utf-8", "latin-1", "cp1252", "mac-roman", "ascii"])
    def test_byte_oriented_codecs_survive_line_splitting(self, encoding):
        assert is_line_safe(encoding) is True

    def test_a_per_line_bom_is_fine(self):
        """The API emits a utf-8-sig BOM on every row, and each line decode strips it."""
        assert is_line_safe("utf-8-sig") is True

    @pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
    def test_wide_codecs_do_not(self, encoding):
        """Splitting on b"\n" cuts their characters in half."""
        assert is_line_safe(encoding) is False

    def test_unknown_codec_is_not_line_safe(self):
        assert is_line_safe("utf8mb4") is False
