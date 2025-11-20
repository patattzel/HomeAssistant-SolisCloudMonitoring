"""Data update coordinator for Solis Cloud Monitoring."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SolisCloudAPI, SolisCloudAPIError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SolisCloudDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Class to manage fetching Solis Cloud data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SolisCloudAPI,
        inverter_serials: list[str],
        inverter_stations: dict[str, str],
    ) -> None:
        """Initialize the coordinator.
        
        Args:
            hass: Home Assistant instance
            api: Solis Cloud API client
            inverter_serials: List of inverter serial numbers to monitor
            inverter_stations: Mapping of inverter serials to station IDs
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.api = api
        self.inverter_serials = inverter_serials
        self.inverter_stations = inverter_stations

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from Solis Cloud API.
        
        Returns:
            Dictionary mapping serial numbers to inverter data
            
        Raises:
            UpdateFailed: When update fails
        """
        data: dict[str, dict[str, Any]] = {}
        station_cache: dict[str, dict[str, Any]] = {}

        try:
            # Fetch data for each inverter
            for serial in self.inverter_serials:
                try:
                    inverter_data = await self.api.get_inverter_details(serial)

                    # Attach station data if station ID is known
                    station_id = self.inverter_stations.get(serial)
                    if station_id:
                        if station_id not in station_cache:
                            try:
                                station_cache[station_id] = await self.api.get_station_detail(
                                    station_id
                                )
                            except SolisCloudAPIError as station_err:
                                _LOGGER.debug(
                                    "Failed to fetch station %s: %s",
                                    station_id,
                                    station_err,
                                )
                        if station_id in station_cache:
                            # Copy to avoid mutating cached payload
                            inverter_data = dict(inverter_data)
                            inverter_data["station_detail"] = station_cache[station_id]

                    data[serial] = inverter_data
                    pac_value = inverter_data.get("pac")
                    try:
                        pac_float = float(pac_value) if pac_value not in (None, "") else None
                    except (TypeError, ValueError):
                        pac_float = None

                    if pac_float is not None:
                        _LOGGER.debug(
                            "Updated data for inverter %s: power=%.2f kW",
                            serial,
                            pac_float,
                        )
                    else:
                        _LOGGER.debug("Updated data for inverter %s", serial)
                except SolisCloudAPIError as err:
                    _LOGGER.warning(
                        "Failed to update inverter %s: %s", serial, err
                    )
                    # Continue with other inverters even if one fails
                    continue

            if not data:
                raise UpdateFailed("Failed to fetch data for any inverter")

            return data

        except SolisCloudAPIError as err:
            raise UpdateFailed(f"Error communicating with Solis Cloud API: {err}") from err
