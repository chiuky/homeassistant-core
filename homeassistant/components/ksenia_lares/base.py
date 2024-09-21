"""Base component for Lares."""

import logging

import aiohttp
from getmac import get_mac_address
from lxml import etree

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, format_mac

from .const import DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)


class LaresBase:
    """The implementation of the Lares base class."""

    def __init__(self, data: dict) -> None:
        """Construct the class."""
        username = data["username"]
        password = data["password"]
        host = data["host"]
        port = data["port"]

        self._auth = aiohttp.BasicAuth(username, password)
        self._ip = host
        self._port = port
        self._host = f"http://{host}:{self._port}"
        self._model = None
        self._zone_descriptions = None
        self._partition_descriptions = None
        self._scenario_descriptions = None
        self._temperature_indoor = None
        self._temperature_outdoor = None
        self._output_descriptions = None

    async def info(self) -> dict | None:
        """Get general info."""
        response = await self.get("info/generalInfo.xml")

        if response is None:
            return None

        mac = get_mac_address(ip=self._ip)
        unique_id = str(mac)

        if mac is None:
            # Fallback to IP addresses when MAC cannot be determined
            unique_id = f"{self._ip}:{self._port}"

        return {
            "mac": mac,
            "id": unique_id,
            "name": response.xpath("/generalInfo/productName")[0].text,
            "info": response.xpath("/generalInfo/info1")[0].text,
            "version": response.xpath("/generalInfo/productHighRevision")[0].text,
            "revision": response.xpath("/generalInfo/productLowRevision")[0].text,
            "build": response.xpath("/generalInfo/productBuildRevision")[0].text,
        }

    async def device_info(self) -> dict | None:
        """Get device info."""
        device_info = await self.info()

        if device_info is None:
            return None

        info = {
            "identifiers": {(DOMAIN, device_info["id"])},
            "name": device_info["name"],
            "manufacturer": MANUFACTURER,
            "model": device_info["name"],
            "sw_version": f'{device_info["version"]}.{device_info["revision"]}.{device_info["build"]}',
            "configuration_url": self._host,
        }

        mac = device_info["mac"]

        if mac is not None:
            info["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(mac))}

        return info

    async def zone_descriptions(self):
        """Get available zones."""
        model = await self.get_model()
        if self._zone_descriptions is None:
            self._zone_descriptions = await self.get_descriptions(
                f"zones/zonesDescription{model}.xml", "/zonesDescription/zone"
            )

        return self._zone_descriptions

    async def zones(self):
        """Get available zones."""
        model = await self.get_model()
        response = await self.get(f"zones/zonesStatus{model}.xml")

        if response is None:
            return None

        zones = response.xpath("/zonesStatus/zone")

        return [
            {
                "status": zone.find("status").text,
                "bypass": zone.find("bypass").text,
            }
            for zone in zones
        ]

    async def output_descriptions(self):
        """Get output descr zones."""
        model = await self.get_model()
        if self._output_descriptions is None:
            self._output_descriptions = await self.get_descriptions(
                f"outputs/outputsDescription{model}.xml", "/outputsDescription/output"
            )

        return self._output_descriptions

    async def outputs(self):
        """Get available zones."""
        model = await self.get_model()
        outputsStatus = await self.get(f"outputs/outputsStatus{model}.xml")

        if outputsStatus is None:
            return None

        outputs = outputsStatus.xpath("/outputsStatus/output")

        return [
            {
                "status": output.find("status").text,
                "type": output.find("type").text,
                "value": output.find("value").text,
                "noPIN": output.find("noPIN").text,
            }
            for output in outputs
        ]

    async def temperatures(self):
        """Get lares temperatures."""
        if self._temperature_indoor is None or self._temperature_outdoor is None:
            response = await self.get("state/laresStatus.xml")
            if response is None:
                return None
            self._temperature_indoor = (
                response.xpath("/laresStatus/temperature/indoor")[0]
                .text.replace("C", "")
                .strip()
            )
            self._temperature_outdoor = (
                response.xpath("/laresStatus/temperature/outdoor")[0]
                .text.replace("C", "")
                .strip()
            )
        return [
            {
                "description": "lares_temperature_indoor",
                "temperatureValue": self._temperature_indoor,
            },
            {
                "description": "lares_temperature_outdoor",
                "temperatureValue": self._temperature_outdoor,
            },
        ]

    async def partitions(self):
        """Get status of partitions."""
        model = await self.get_model()
        response = await self.get(f"partitions/partitionsStatus{model}.xml")

        if response is None:
            return None

        partitions = response.xpath("/partitionsStatus/partition")

        return [
            {
                "status": partition.text,
            }
            for partition in partitions
        ]

    async def partition_descriptions(self):
        """Get available partitions."""
        model = await self.get_model()

        if self._partition_descriptions is None:
            self._partition_descriptions = await self.get_descriptions(
                f"partitions/partitionsDescription{model}.xml",
                "/partitionsDescription/partition",
            )

        return self._partition_descriptions

    async def get_descriptions(self, path: str, element: str) -> list | None:
        """Get descriptions."""
        response = await self.get(path)

        if response is None:
            return None

        content = response.xpath(element)
        return [item.text for item in content]

    async def scenarios(self):
        """Get status of scenarios."""
        response = await self.get("scenarios/scenariosOptions.xml")

        if response is None:
            return None

        scenarios = response.xpath("/scenariosOptions/scenario")

        return [
            {
                "id": idx,
                "enabled": scenario.find("abil").text == "TRUE",
                "noPin": scenario.find("nopin").text == "TRUE",
            }
            for idx, scenario in enumerate(scenarios)
        ]

    async def scenario_descriptions(self):
        """Get descriptions of scenarios."""
        if self._scenario_descriptions is None:
            self._scenario_descriptions = await self.get_descriptions(
                "scenarios/scenariosDescription.xml", "/scenariosDescription/scenario"
            )

        return self._scenario_descriptions

    async def activate_scenario(self, scenario: int, pinCode: str) -> bool:
        """Activate the given scenarios, requires the alarm code."""
        params = {"macroId": scenario}

        return await self.send_command("setMacro", pinCode, params)

    async def bypass_zone(self, zoneId: int, pinCode: str, bypass: bool) -> bool:
        """Activate the given scenarios, requires the alarm code."""
        params = {
            "zoneId": zoneId + 1,  # Lares uses index starting with 1
            "zoneValue": 1 if bypass else 0,
        }

        return await self.send_command("setByPassZone", pinCode, params)

    async def switch_output(self, outputId: int, pinCode: str, status: bool) -> bool:
        """Activate the given scenarios, requires the alarm code."""
        params = {
            "outputId": outputId,  # Lares output uses index starting with 0
            "outputValue": 255 if status else 0,
        }

        return await self.send_command("setOutput", pinCode, params)

    async def get_model(self) -> str:
        """Get model information."""
        if self._model is None:
            info = await self.info()
            if info is not None:
                if info["name"].endswith("128IP"):
                    self._model = "128IP"
                elif info["name"].endswith("48IP"):
                    self._model = "48IP"
                else:
                    self._model = "16IP"

        return self._model

    async def send_command(
        self, command: str, pinCode: str, params: dict[str, int]
    ) -> bool:
        """Send Command."""
        urlparam = "".join(f"&{k}={v}" for k, v in params.items())
        path = f"cmd/cmdOk.xml?cmd={command}&pin={pinCode}&redirectPage=/xml/cmd/cmdError.xml{urlparam}"

        _LOGGER.debug("Sending command %s", path)

        response = await self.get(path)
        cmd = response.xpath("/cmd")

        if cmd is None or cmd[0].text != "cmdSent":
            _LOGGER.error("Command send failed: %s", response)
            return False

        return True

    async def get(self, path):
        """Get method."""
        url = f"{self._host}/xml/{path}"

        try:
            async with (
                aiohttp.ClientSession(auth=self._auth) as session,
                session.get(url=url) as response,
            ):
                xml = await response.read()
                return etree.fromstring(xml)  # noqa: S320

        except aiohttp.ClientConnectorError as conn_err:
            _LOGGER.debug("Host %s: Connection error %s", self._host, str(conn_err))
        except:  # pylint: disable=bare-except  # noqa: E722
            _LOGGER.debug("Host %s: Unknown exception occurred", self._host)
        return None
