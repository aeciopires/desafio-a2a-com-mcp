from __future__ import annotations

import pytest

from mcp_server import config
from mcp_server.repository import Repository


def test_repository_loads_seed_data(data_dir):
    repo = Repository.from_data_dir(data_dir)
    assert set(repo.rooms) == {"sala-aquario", "sala-porao", "sala-garagem", "sala-fusca", "sala-mirante"}
    assert [r.id for r in repo.reservations()] == ["res-0001", "res-0002"]
    assert repo.policy_text.startswith("versao: 2026-11-01")


def test_new_reservations_get_sequential_ids(data_dir):
    repo = Repository.from_data_dir(data_dir)
    first = repo.add("sala-aquario", "2026-11-03T09:00:00-03:00", "2026-11-03T10:00:00-03:00", "Doc")
    second = repo.add("sala-porao", "2026-11-03T09:00:00-03:00", "2026-11-03T10:00:00-03:00", "Doc")
    assert (first.id, second.id) == ("res-0003", "res-0004")
    assert len(repo.reservations()) == 4


def test_version_comes_from_the_version_file():
    assert config.get_version() == (config._find_version_file().read_text().strip())  # noqa: SLF001


def test_missing_secret_fails_with_instructions(monkeypatch):
    monkeypatch.delenv("REQUEST_STATE_SECRET", raising=False)
    with pytest.raises(config.ConfigError, match="make secret"):
        config.load_settings()


def test_short_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("REQUEST_STATE_SECRET", "too-short")
    with pytest.raises(config.ConfigError, match="at least 32 bytes"):
        config.load_settings()


@pytest.mark.parametrize("ttl", ["299", "1801"])
def test_ttl_must_be_between_5_and_30_minutes(monkeypatch, ttl):
    monkeypatch.setenv("REQUEST_STATE_TTL_SECONDS", ttl)
    with pytest.raises(config.ConfigError, match="REQUEST_STATE_TTL_SECONDS"):
        config.load_settings()


def test_port_can_be_overridden(monkeypatch):
    monkeypatch.setenv("MCP_PORT", "7311")
    assert config.load_settings().port == 7311


def test_invalid_port_is_reported(monkeypatch):
    monkeypatch.setenv("MCP_PORT", "abc")
    with pytest.raises(config.ConfigError, match="MCP_PORT must be an integer"):
        config.load_settings()
