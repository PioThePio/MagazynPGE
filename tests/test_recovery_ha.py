from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import State
from homeassistant.util import dt as dt_util

from custom_components.pge_storage.hourly import hour_floor
from custom_components.pge_storage.recovery import reconcile, validate
from tests.test_recovery import example

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_native_store_roundtrip_and_failed_checkpoint_do_not_mutate_ledger(ha):
    hass, _ = ha
    now = dt_util.utcnow()
    for entity in ("sensor.recovery_i", "sensor.recovery_e"):
        hass.states.async_set(entity, "0", {"unit_of_measurement": "kWh"})
    flow = await hass.config_entries.flow.async_init(
        "pge_storage", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": "sensor.recovery_i",
            "export_entity_id": "sensor.recovery_e",
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    manager = result["result"].runtime_data
    sources = manager.sources
    end = hour_floor(now)
    cache, boundaries, start, end = example(end - timedelta(hours=7))
    cache["sources"] = sources
    cache = reconcile(cache, boundaries, {}, now)
    manager.recovery_cache = cache
    await manager.store.async_save(manager._payload())
    stored = await manager.store.async_load()
    restored = validate(stored["recovery_cache"], sources, now)
    assert restored["blocks"][0]["net_kwh"] == "-6"
    exported = manager.export()
    assert exported["recovery_cache"]["blocks"][0]["net_kwh"] == "-6"
    # Source changes are not committed if persistence fails; the last durable
    # pair remains available for retry after restart.
    before = deepcopy(manager.recovery_cache)
    with patch.object(
        manager.store, "async_save", new=AsyncMock(side_effect=OSError("write failed"))
    ):
        with pytest.raises(OSError):
            await manager._checkpoint_recovery(now)
    assert manager.recovery_cache == before
    assert (await manager.store.async_load())["recovery_cache"] == stored[
        "recovery_cache"
    ]


async def test_only_actual_recorder_boundary_history_can_replace_estimate(ha):
    import asyncio

    from homeassistant.components.recorder.core import SynchronizeTask
    from homeassistant.const import EVENT_STATE_CHANGED
    from homeassistant.helpers.recorder import get_instance

    from custom_components.pge_storage.hourly import make_hour
    from custom_components.pge_storage.recovery import proven_hours

    hass, _ = ha
    end = hour_floor(dt_util.utcnow())
    cache, boundaries, start, end = example(end - timedelta(hours=7))
    cache["sources"] = {"import": "sensor.repair_i", "export": "sensor.repair_e"}
    cache = reconcile(cache, boundaries, {}, end)
    rows = [
        make_hour(start + timedelta(hours=i), 10 if i == 1 else 0, 5 if i == 1 else 0)
        for i in range(7)
    ]
    hours = {r["start"]: r for r in rows}
    assert await proven_hours(hass, cache["sources"], cache, hours) == set()
    for i in range(8):
        at = start + timedelta(hours=i)
        for direction, entity in cache["sources"].items():
            amount = (1000 if direction == "import" else 500) + (
                10 if direction == "import" else 5
            ) * (i >= 2)
            state = State(
                entity, str(amount), {"unit_of_measurement": "kWh"}, last_updated=at
            )
            hass.bus.async_fire_internal(
                EVENT_STATE_CHANGED,
                {"entity_id": entity, "old_state": None, "new_state": state},
                time_fired=at.timestamp(),
            )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    proof = await proven_hours(hass, cache["sources"], cache, hours)
    assert proof == set(hours)
    assert reconcile(cache, {}, hours, end, proof)["blocks"][0]["status"] == "replaced"
