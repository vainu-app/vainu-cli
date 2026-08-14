"""Tests for organization field metadata helpers and CLI."""

import json

import responses as resp
from click.testing import CliRunner
from conftest import BASE_URL, ORGANIZATION_FIELDS_RESPONSE

from vainu_cli.cli import main
from vainu_cli.fields_commands import (
    filter_organization_fields,
    format_fields_summary,
    format_fields_table,
)


class TestOrganizationFieldHelpers:
    def test_filter_filterable_only(self):
        filtered = filter_organization_fields(
            ORGANIZATION_FIELDS_RESPONSE,
            filterable=True,
        )
        assert [item["api"]["v3"]["path"] for item in filtered] == ["contacts"]

    def test_filter_returnable_only(self):
        filtered = filter_organization_fields(
            ORGANIZATION_FIELDS_RESPONSE,
            returnable=True,
        )
        paths = [item["api"]["v3"]["path"] for item in filtered]
        assert paths == ["address.street", "contacts.email"]

    def test_filter_permission_gated(self):
        filtered = filter_organization_fields(
            ORGANIZATION_FIELDS_RESPONSE,
            permission_gated=True,
        )
        assert len(filtered) == 1
        assert filtered[0]["api"]["v3"]["path"] == "contacts.email"

    def test_format_table_includes_availability_columns(self):
        table = format_fields_table(ORGANIZATION_FIELDS_RESPONSE)
        assert "address.street" in table
        assert "contacts.email" in table
        assert "data_catalogue_contact_details" in table

    def test_format_summary_counts_permission_gated(self):
        summary = format_fields_summary(ORGANIZATION_FIELDS_RESPONSE)
        assert "Total fields: 3" in summary
        assert "Permission-gated fields:" in summary
        assert "data_catalogue_contact_details: 1 fields" in summary


class TestFieldsCli:
    @resp.activate
    def test_fields_organizations_table_default(self):
        resp.add(
            resp.GET,
            f"{BASE_URL}/v3/organizations_fields/?api_versions=v3",
            json=ORGANIZATION_FIELDS_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "fields", "organizations"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "path" in result.output
        assert "address.street" in result.output
        assert "contacts.email" in result.output

    @resp.activate
    def test_fields_organizations_json_view(self):
        resp.add(
            resp.GET,
            f"{BASE_URL}/v3/organizations_fields/?api_versions=v3",
            json=ORGANIZATION_FIELDS_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "fields", "organizations", "--view", "json", "--filterable"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["api"]["v3"]["path"] == "contacts"
