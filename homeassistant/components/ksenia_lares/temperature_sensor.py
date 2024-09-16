"""Provide support for Lares temperatures."""

from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DATA_TEMPERATURES, DOMAIN

SCAN_INTERVAL = timedelta(seconds=10)
DEFAULT_DEVICE_CLASS = "motion"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors attached to a Lares alarm device from a config entry."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    device_info = await coordinator.client.device_info()

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_refresh()

    async_add_entities(
        LaresTemperatureSensor(
            coordinator, idx, temperature["description"], device_info
        )
        for idx, temperature in enumerate(coordinator.data[DATA_TEMPERATURES])
    )


class LaresTemperatureSensor(CoordinatorEntity, Entity):
    """Implementat of a Lares temperature sensor."""

    def __init__(self, coordinator, idx, description, device_info) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._coordinator = coordinator
        self._description = description
        self._idx = idx

        self._attr_icon = "mdi:shield"
        self._attr_device_info = device_info
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self.attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        # Hide sensor if it has no description
        is_inactive = not self._description

        self._attr_entity_registry_enabled_default = not is_inactive
        self._attr_entity_registry_visible_default = not is_inactive

    @property
    def unique_id(self):
        """Return Unique ID string."""
        return f"lares_temperature_sensor_{self._idx}"

    @property
    def name(self):
        """Return the name of this entity."""
        return self._description

    @property
    def native_value(self):
        """Return the status of this partition."""
        return self._coordinator.data[DATA_TEMPERATURES][self._idx]["temperatureValue"]
