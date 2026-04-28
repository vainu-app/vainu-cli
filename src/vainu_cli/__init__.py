"""vainu-cli — CLI and Python client for the Vainu company data API."""

from vainu_cli._async_client import (
    AsyncResult,
    VainuAPIKeyClient,
    VainuJWTAPIClient,
    VainuOAuthAPIClient,
)
from vainu_cli.common import AsyncJobState
from vainu_cli._sync_client import (
    AsyncResult as SyncAsyncResult,
    VainuAPIKeySyncClient,
    VainuJWTSyncClient,
    VainuOAuthSyncClient,
)
from vainu_cli._version import __version__

SyncAsyncJobState = AsyncJobState

__all__ = [
    "__version__",
    # Async clients
    "VainuAPIKeyClient",
    "VainuJWTAPIClient",
    "VainuOAuthAPIClient",
    "AsyncJobState",
    "AsyncResult",
    # Sync clients
    "VainuAPIKeySyncClient",
    "VainuJWTSyncClient",
    "VainuOAuthSyncClient",
    "SyncAsyncJobState",
    "SyncAsyncResult",
]
