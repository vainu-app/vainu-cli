"""Shared test fixtures."""

import pytest
from click.testing import CliRunner

BASE_URL = "https://api.vainu.io/api"
JWT_REFRESH_URL = "https://api.vainu.io/api/token_authentication/refresh/"
OAUTH_TOKEN_URL = "https://api.vainu.io/api/oauth/token/"
OAUTH_REVOKE_URL = "https://api.vainu.io/api/oauth/revoke_token/"


@pytest.fixture(autouse=True)
def _isolate_auth_store(monkeypatch, tmp_path):
    """Make sure tests never see / write real user credentials.

    Forces the file-backend, points it at a tmp dir, and clears any VAINU_*
    env vars that could otherwise leak from the developer's shell.
    """
    monkeypatch.setenv("VAINU_AUTH_STORE", "file")
    # Off by default so token-refresh assertions count real network calls;
    # cache tests opt in with `token_cache=True`.
    monkeypatch.setenv("VAINU_TOKEN_CACHE", "0")
    monkeypatch.setattr(
        "vainu_cli.auth.storage.user_config_path",
        lambda *_, **__: tmp_path / "vainu-config",
    )
    for var in (
        "VAINU_API_KEY",
        "VAINU_CLIENT_ID",
        "VAINU_CLIENT_SECRET",
        "VAINU_JWT_REFRESH_TOKEN",
        "VAINU_ACCESS_TOKEN",
        "VAINU_REFRESH_TOKEN",
        "VAINU_TOKEN_EXPIRES_AT",
        "VAINU_AUTH_METHOD",
        "VAINU_BASE_URL",
        "VAINU_SCOPE",
    ):
        monkeypatch.delenv(var, raising=False)


COMPANIES_RESPONSE = {
    "result": [
        {
            "business_id": "FI01320292",
            "name": "Test Company Oy",
            "country": "FI",
        }
    ],
    "count": 1,
    "next": None,
}

ORGANIZATIONS_RESPONSE = {
    "result": [{"business_id": "FI01320292", "name": "Test Org"}],
    "count": 1,
    "next": None,
}

SIGNALS_NEWS_RESPONSE = [
    {
        "id": "65f0a1b2c3d4e5f6a7b8c9d0",
        "title": "Test Company Oy raises 12 MEUR",
        "content": "Test Company Oy announced today that it has closed a...",
        "link": "https://example.com/articles/test-company-funding",
        "vainu_date": "2026-04-22T08:15:00",
        "tags": [{"id": 43543, "value": "Funding"}],
        "organizations": [
            {
                "business_id": "FI01320292",
                "country": "FI",
                "logo_url": "https://logos.vainu.io/FI01320292.png",
                "name": "Test Company Oy",
            }
        ],
    }
]

SIGNALS_DATA_CHANGES_RESPONSE = [
    {
        "id": "66001a2b3c4d5e6f7a8b9c0d",
        "title": "New financial statement",
        "content": "Test Company Oy has registered a new financial statement.",
        "vainu_date": "2026-03-30T00:00:00",
        "tags": [{"id": 8000037, "value": "New Financial Statement"}],
        "organizations": [
            {
                "business_id": "FI01320292",
                "country": "FI",
                "logo_url": "https://logos.vainu.io/FI01320292.png",
                "name": "Test Company Oy",
            }
        ],
        "dynamic_values": [{"key": "new_financial_statement", "value": "2025"}],
    }
]

ENRICHMENT_AGENT_RESPONSE = {
    "response": {
        "main_business_activity": "Test Company Oy is a mobile game developer that creates …",
        "products_and_services": "Test Company Oy's primary products are its mobile games …",
    }
}

ENRICHMENT_AGENT_JSONL_RESPONSE = (
    '{"response":{"main_business_activity":"Test Company Oy is a mobile game developer …"}}'
)

SIGNALS_JSONL_RESPONSE = (
    '{"id":"65f0a1b2c3d4e5f6a7b8c9d0","title":"Test Company Oy raises 12 MEUR"}\n'
    '{"id":"66001a2b3c4d5e6f7a8b9c0d","title":"New financial statement"}'
)

JSONL_RESPONSE = (
    '{"business_id":"FI01320292","name":"Test Org"}\n'
    '{"business_id":"FI99999999","name":"Another Org"}'
)

# Blank lines and non-ASCII content, to pin line filtering and UTF-8 decoding in
# the streaming paths — requests guesses ISO-8859-1 when a charset is missing.
JSONL_STREAM_RESPONSE = (
    '{"id":"1","title":"Höyrytys Oy rakentaa tuotantolaitoksen"}\n'
    "\n"
    '{"id":"2","title":"Alva-yhtiöt Oy kilpailuttaa puhtaanapidon"}\n'
)
JSONL_STREAM_LINES = [
    '{"id":"1","title":"Höyrytys Oy rakentaa tuotantolaitoksen"}',
    '{"id":"2","title":"Alva-yhtiöt Oy kilpailuttaa puhtaanapidon"}',
]

CSV_RESPONSE = "business_id,name\nFI01320292,Test Org\nFI99999999,Another Org\n"

ASYNC_JOB_ACCEPTED = {"state": "accepted", "progress": 0}
ASYNC_JOB_PROCESS = {"state": "process", "progress": 50}
ASYNC_JOB_COMPLETED = {
    "state": "completed",
    "download_link": "https://downloads.vainu.io/result.json",
    "duration": 5,
}
ASYNC_JOB_SUBMIT_RESPONSE = {"link": f"{BASE_URL}/v2/companies/async/job123/"}

OAUTH_TOKEN_RESPONSE = {
    "access_token": "test-access-token",
    "token_type": "Bearer",
    "expires_in": 3600,
}

JWT_TOKEN_RESPONSE = {
    "access": "test-access-token",
    "expires_in": 3600,
}

ORGANIZATION_LISTS_RESPONSE = [
    {
        "id": "63d8de4eb7dfe9f5896fa539",
        "name": "Finland + Revenue +1M EUR",
        "country": "FI",
        "type": "dynamic-organization-list",
        "query": '{"?GTE": {"financial_data.revenue": 1000000}}',
        "created": "2023-01-31T09:24:30.201000",
        "modified": "2023-04-29T11:48:51.054000",
        "privileges": {"current": "owner", "shared_count": 0},
        "migrated_from_legacy_list": None,
    }
]

ORGANIZATION_FIELDS_RESPONSE = [
    {
        "main_category": "basic",
        "sub_category": "main_location",
        "api": {
            "v2": {"path": "address", "name": "address"},
            "v3": {"path": "address.street", "name": "street"},
        },
        "names": {
            "aliases": [],
            "translations": {"en": "Street (Main Postal Address)"},
        },
        "countries": ["FI"],
        "databases": ["FI"],
        "application_availability": ["connector", "export", "profile"],
        "description": "Street part of the main postal address.",
        "meta_data": {
            "status": "active",
            "obsoleted_by": None,
            "normalisation": "raw",
            "type": "string",
            "sources": {"FI": ["registry"]},
            "allowed_operators": ["EQ", "CONTAINS"],
            "default_operator": "STARTSWITH",
        },
        "match_group": None,
        "requires_permission": None,
        "filter_values": None,
    },
    {
        "main_category": "contacts",
        "sub_category": "contacts",
        "api": {
            "v2": {"path": None, "name": None},
            "v3": {"path": "contacts", "name": "contacts"},
        },
        "names": {"aliases": [], "translations": {"en": "Contacts"}},
        "countries": ["FI"],
        "databases": ["FI"],
        "application_availability": ["filter"],
        "description": "Contacts attached to the company.",
        "meta_data": {
            "status": "active",
            "obsoleted_by": None,
            "normalisation": "raw",
            "type": "object_list",
            "sources": {"FI": ["web", "linkedin"]},
            "allowed_operators": ["EXISTS", "ISNULL"],
            "default_operator": "EXISTS",
        },
        "match_group": None,
        "requires_permission": None,
        "filter_values": None,
    },
    {
        "main_category": "contacts",
        "sub_category": "contacts",
        "api": {
            "v2": {"path": None, "name": None},
            "v3": {"path": "contacts.email", "name": "email"},
        },
        "names": {"aliases": [], "translations": {"en": "Email (Contact)"}},
        "countries": ["FI"],
        "databases": ["FI"],
        "application_availability": ["export", "profile"],
        "description": "Email address of a contact.",
        "meta_data": {
            "status": "active",
            "obsoleted_by": None,
            "normalisation": "raw",
            "type": "string",
            "sources": {"FI": ["web"]},
            "allowed_operators": ["EXISTS", "ISNULL"],
            "default_operator": "EXISTS",
        },
        "match_group": "contacts",
        "requires_permission": ["data_catalogue_contact_details"],
        "filter_values": None,
    },
]

STATIC_LIST_RESPONSE = {
    "id": "63d8de4eb7dfe9f5896fa540",
    "name": "My Static List",
    "country": "FI",
    "type": "static-organization-list",
    "query": "",
    "created": "2023-01-31T09:24:30.201000",
    "modified": "2023-04-29T11:48:51.054000",
    "privileges": {"current": "owner", "shared_count": 0},
    "migrated_from_legacy_list": None,
}

DYNAMIC_LIST_RESPONSE = {
    "id": "69e61e048c5d1ae30b426a1b",
    "name": "Swedish Manufacturers",
    "country": "SE",
    "type": "dynamic-organization-list",
    "query": '{"?ALL": [{"?IN": {"official_industries.code": ["25"]}}]}',
    "created": "2026-04-20T12:37:24.397523",
    "modified": "2026-04-20T12:37:24.403035",
    "privileges": {"current": "owner", "shared_count": 0},
    "migrated_from_legacy_list": None,
    "scoring": None,
    "query_metadata": None,
}


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()
