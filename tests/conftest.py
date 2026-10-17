import asyncio
import socket
from pathlib import Path

import pytest_asyncio
from homeassistant import bootstrap, loader
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

ROOT = Path(__file__).resolve().parents[1]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def ha(tmp_path_factory):
    directory = tmp_path_factory.mktemp("ha-real")
    await asyncio.to_thread(
        (directory / "custom_components").symlink_to,
        ROOT / "custom_components",
        target_is_directory=True,
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    hass = HomeAssistant(str(directory))
    loader.async_setup(hass)
    hass.config.skip_pip = True
    config = {
        "homeassistant": {
            "name": "PGE isolated test",
            "time_zone": "Europe/Warsaw",
            "country": "PL",
            "latitude": 52.23,
            "longitude": 21.01,
            "elevation": 100,
        },
        "http": {"server_host": "127.0.0.1", "server_port": port},
        "frontend": {},
        "recorder": {
            "db_url": f"sqlite:///{directory / 'test.db'}",
            "commit_interval": 0,
            "auto_purge": False,
        },
    }
    try:
        assert await bootstrap.async_from_config_dict(config, hass) is hass
        assert await async_setup_component(hass, "pge_storage", {})
        await hass.async_start()
        await hass.async_block_till_done()
        yield hass, port
    finally:
        await hass.async_stop(force=True)
        await hass.async_block_till_done()
