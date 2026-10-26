"""Recorder reads: bounded real states, never statistics or interpolated values."""

from datetime import datetime, timedelta
from decimal import Decimal
from functools import partial

from homeassistant.components.recorder import history, statistics
from homeassistant.core import HomeAssistant
from homeassistant.helpers.recorder import get_instance

from .ledger import LedgerError, Sample, boundary, combine_counters, energy, energy_text

ENERGY_FACTORS = {"Wh": Decimal("0.001"), "kWh": Decimal(1), "MWh": Decimal(1000)}


def sample_from_state(state) -> Sample:
    if state is None:
        raise LedgerError("missing_source", "Licznik energii jest niedostępny.")
    factor = ENERGY_FACTORS.get(state.attributes.get("unit_of_measurement"))
    if factor is None:
        raise LedgerError(
            "wrong_unit",
            "Licznik musi mierzyć energię w Wh, kWh lub MWh, nie moc W/kW ani procenty.",
        )
    try:
        value = energy(state.state) * factor
    except LedgerError:
        raise LedgerError(
            "invalid_history", "Stan licznika jest niedostępny lub nienumeryczny."
        ) from None
    return Sample(energy_text(value), state.last_updated.isoformat())


def select_sample(states: list, day: str, max_age_hours: int) -> Sample:
    """Use the latest recorded state, including unknown/unavailable as errors."""
    end = boundary(day)
    start = end - timedelta(hours=max_age_hours)
    candidates = [state for state in states if start <= state.last_updated < end]
    if not candidates:
        raise LedgerError(
            "missing_history",
            f"Brak próbki Recorder w ciągu {max_age_hours} h przed końcem dnia {day}. "
            "Historia mogła zostać usunięta. Statystyki godzinowe nie zastąpią odczytu.",
        )
    state = max(candidates, key=lambda state: state.last_updated)
    return sample_from_state(state)


async def async_read_samples(
    hass: HomeAssistant, sources: dict, day: str, max_age_hours: int, now: datetime
) -> dict[str, Sample]:
    end = boundary(day)
    if end > now:
        raise LedgerError("future_date", "Wybierz zakończony dzień.")
    states = await get_instance(hass).async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            end - timedelta(hours=max_age_hours),
            end,
            list(sources.values()),
            include_start_time_state=False,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
    )
    samples = {}
    for direction, entity_id in sources.items():
        try:
            samples[direction] = select_sample(
                states.get(entity_id, []), day, max_age_hours
            )
        except LedgerError as err:
            raise LedgerError(err.code, f"{direction} ({entity_id}): {err}") from err
    return samples


async def async_read_counters(hass, sources, day, max_age_hours, now) -> Sample:
    samples = await async_read_samples(hass, sources, day, max_age_hours, now)
    return combine_counters(samples["import"], samples["export"])


async def async_statistics_metadata(hass: HomeAssistant, entity_id: str) -> dict:
    result = await get_instance(hass).async_add_executor_job(
        partial(statistics.get_metadata, hass, statistic_ids={entity_id})
    )
    metadata = result.get(entity_id)
    return {
        "has_statistics_metadata": metadata is not None,
        "has_mean": bool(metadata and metadata[1].get("has_mean")),
        "has_sum": bool(metadata and metadata[1].get("has_sum")),
        "note": "Metadane nie dowodzą pokrycia daty. Próbka faktury pochodzi ze stanów Recorder; rozliczenie magazynu wymaga osobnych przyrostów godzinowych sum obu liczników.",
    }
