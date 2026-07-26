"""Supabase (PostgREST) access.

A per-request client is built with the *anon* key and the caller's JWT, so
every query executes under the caller's RLS context. The service-role key is
never used by this API — it is reserved for the offline pipeline sync job.
"""
from typing import Protocol

from fastapi import Depends
from supabase import Client, create_client

from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings


class DbClient(Protocol):
    """Minimal surface of the supabase-py client this app uses (enables fakes)."""

    def table(self, name: str):  # noqa: ANN001, ANN201 - mirrors supabase-py fluent API
        ...


def get_db(
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Client:
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    # Scope all PostgREST calls to the caller for RLS enforcement.
    client.postgrest.auth(user.token)
    return client
