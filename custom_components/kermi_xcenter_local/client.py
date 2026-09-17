"""HTTP client for the Kermi x-center local API."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout, CookieJar

from .const import (
    BUFFER_FUNCTION_DHW,
    BUFFER_FUNCTION_HEATING,
    DESTINATION_ID,
    DEVICE_TYPE_BUFFER,
    DEVICE_TYPE_FRESH_WATER,
    DEVICE_TYPE_HEAT_PUMP,
    DEVICE_TYPE_IFM,
)

_LOGGER = logging.getLogger(__name__)

_RETRYABLE_STATUS = {404, 405}


class KermiError(Exception):
    """Base error for the Kermi API."""


class KermiAuthError(KermiError):
    """Login rejected or session expired permanently."""


class KermiConnectionError(KermiError):
    """Device not reachable."""


@dataclass
class KermiDeviceData:
    """One x-center device with its live datapoints."""

    device_id: str
    name: str
    device_type: int
    serial: str | None
    software_version: str | None
    model: str
    values: dict[str, Any] = field(default_factory=dict)
    display_values: dict[str, Any] = field(default_factory=dict)


def _as_list(obj: Any) -> list[Any]:
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict) and "$values" in obj:
        return obj.get("$values") or []
    return [obj]


def _sanitize(value: Any) -> Any:
    if isinstance(value, str) and value.lower() in ("nan", "inf", "-inf", ""):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _looks_numeric(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.strip().replace(",", "."))
        except ValueError:
            return False
        return True
    return False


def _extract_value(val_obj: dict[str, Any]) -> Any:
    """Prefer a numeric payload over a display label such as 'Komfort'."""
    value = val_obj.get("Value")
    numeric = val_obj.get("NumericValue")
    if _looks_numeric(value):
        return _sanitize(value)
    if numeric is not None:
        return _sanitize(numeric)
    return _sanitize(value)


def _buffer_model(device: dict[str, Any]) -> str:
    wizard_str = (device.get("CustomProperties") or {}).get("WizardAnswer") or ""
    if wizard_str:
        try:
            wizard = json.loads(wizard_str)
            function = wizard.get("PowermoduleFunctionType")
            if function == BUFFER_FUNCTION_DHW:
                return "Puffersystem Trinkwasser"
            if function == BUFFER_FUNCTION_HEATING:
                return "Puffersystem Heizen"
        except (TypeError, ValueError):
            pass
    return "Puffersystem"


def _model_for(device: dict[str, Any]) -> str:
    dtype = device.get("DeviceType", DEVICE_TYPE_IFM)
    if dtype == DEVICE_TYPE_HEAT_PUMP:
        return device.get("Name") or "x-change"
    if dtype == DEVICE_TYPE_BUFFER:
        return _buffer_model(device)
    if dtype == DEVICE_TYPE_FRESH_WATER:
        return "Frischwasserstation"
    if dtype == DEVICE_TYPE_IFM:
        return "x-center Interfacemodul"
    return device.get("Name") or f"DeviceType {dtype}"


def _normalize_host(host: str, port: int) -> tuple[str, int]:
    host = host.strip().removeprefix("http://").removeprefix("https://")
    host = host.split("/")[0]
    if host.startswith("[") and "]" in host:
        # IPv6 like [::1]:8080
        bracket, rest = host.rsplit("]", 1)
        host_part = bracket + "]"
        if rest.startswith(":") and rest[1:].isdigit():
            return host_part, int(rest[1:])
        return host_part, port
    if host.count(":") == 1:
        host_part, maybe_port = host.rsplit(":", 1)
        if maybe_port.isdigit():
            return host_part, int(maybe_port)
    return host, port


class KermiClient:
    """Talks to the x-center HTTP API with cookie login."""

    def __init__(
        self,
        host: str,
        password: str,
        port: int = 80,
        session: ClientSession | None = None,
    ) -> None:
        host, port = _normalize_host(host, port)
        self._host = host
        self._password = password
        self._port = port
        if port == 443:
            self._base = f"https://{host}/api"
        elif port == 80:
            self._base = f"http://{host}/api"
        else:
            scheme = "https" if port == 443 else "http"
            self._base = f"{scheme}://{host}:{port}/api"
        self._session = session
        self._owns_session = session is None

    def _ensure_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                cookie_jar=CookieJar(unsafe=True),
                timeout=ClientTimeout(total=25),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "HomeAssistant-Kermi/0.1.1",
                },
            )
            self._owns_session = True
        return self._session

    async def async_close(self) -> None:
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def async_login(self) -> None:
        last_error: Exception | None = None
        for with_dest in (True, False):
            try:
                raw = await self._request_once(
                    "Security/Login",
                    {"Password": self._password},
                    method="POST",
                    with_dest=with_dest,
                    auth=False,
                )
            except KermiError as exc:
                last_error = exc
                _LOGGER.debug("Login dest=%s failed: %s", with_dest, exc)
                continue
            if isinstance(raw, dict) and raw.get("isValid"):
                return
            last_error = KermiAuthError("Login rejected")
        if isinstance(last_error, KermiError):
            raise last_error
        raise KermiAuthError("Login rejected")

    async def async_update(self) -> dict[str, KermiDeviceData]:
        """Login (if needed), list devices, and read live values."""
        await self.async_login()
        devices = await self._load_devices()

        result: dict[str, KermiDeviceData] = {}
        for device in devices:
            if not isinstance(device, dict):
                continue
            device_id = device.get("DeviceId")
            if not device_id:
                continue
            parsed = KermiDeviceData(
                device_id=device_id,
                name=device.get("Name") or "Kermi",
                device_type=int(device.get("DeviceType") or 0),
                serial=(device.get("Serial") or "").strip() or None,
                software_version=device.get("SoftwareVersion"),
                model=_model_for(device),
            )
            for category in (0, 1):
                try:
                    bundles = await self._request(
                        "Menu/GetBundlesByCategory",
                        {"DeviceId": device_id, "Category": category},
                        methods=("POST",),
                    )
                except KermiError as exc:
                    _LOGGER.warning(
                        "GetBundlesByCategory failed for %s cat %s: %s",
                        parsed.name,
                        category,
                        exc,
                    )
                    continue
                self._ingest_bundles(parsed, bundles)
            result[device_id] = parsed
        if not result:
            raise KermiError("No devices returned by x-center")
        return result

    async def _load_devices(self) -> list[Any]:
        variants: tuple[tuple[str, bool, dict[str, Any] | None], ...] = (
            ("GET", True, None),
            ("POST", True, {}),
            ("GET", False, None),
            ("POST", False, {}),
        )
        last_error: KermiError | None = None
        for method, with_dest, payload in variants:
            try:
                data = await self._request_once(
                    "Device/GetAllDevices",
                    payload,
                    method=method,
                    with_dest=with_dest,
                )
            except KermiError as exc:
                last_error = exc
                _LOGGER.debug("GetAllDevices %s dest=%s failed: %s", method, with_dest, exc)
                continue
            devices = _as_list(data)
            if devices:
                return devices
        _LOGGER.debug("GetAllDevices failed, falling back to GetFavorites")
        try:
            return await self._devices_from_favorites()
        except KermiError as exc:
            raise last_error or exc from exc

    async def _devices_from_favorites(self) -> list[dict[str, Any]]:
        raw = await self._request(
            "Favorite/GetFavorites",
            {"WithDetails": True, "OnlyHomeScreen": False},
            methods=("POST",),
        )
        by_id: dict[str, dict[str, Any]] = {}
        for item in _as_list(raw):
            if not isinstance(item, dict):
                continue
            cfg = item.get("DatapointConfig") if isinstance(item.get("DatapointConfig"), dict) else {}
            device_id = item.get("DeviceId") or cfg.get("DeviceId")
            if not device_id:
                continue
            name = item.get("Name") or item.get("DisplayName") or cfg.get("DisplayName") or "Kermi"
            dtype = item.get("DeviceType")
            if dtype is None:
                dtype = cfg.get("DeviceType") or 0
            current = by_id.get(device_id)
            if current is None or (current.get("Name") == "Kermi" and name != "Kermi"):
                by_id[device_id] = {
                    "DeviceId": device_id,
                    "Name": name,
                    "DeviceType": int(dtype or 0),
                    "Serial": item.get("Serial"),
                    "SoftwareVersion": item.get("SoftwareVersion"),
                }
        if DESTINATION_ID not in by_id:
            by_id[DESTINATION_ID] = {
                "DeviceId": DESTINATION_ID,
                "Name": "x-center Interfacemodul",
                "DeviceType": DEVICE_TYPE_IFM,
                "Serial": None,
                "SoftwareVersion": None,
            }
        if not by_id:
            raise KermiError("GetFavorites returned no devices")
        return list(by_id.values())

    def _ingest_bundles(self, device: KermiDeviceData, bundles: Any) -> None:
        for bundle in _as_list(bundles):
            if not isinstance(bundle, dict):
                continue
            for datapoint in _as_list(bundle.get("Datapoints")):
                if not isinstance(datapoint, dict):
                    continue
                cfg = datapoint.get("Config") or datapoint.get("DatapointConfig") or {}
                val_obj = datapoint.get("DatapointValue") or {}
                if not isinstance(cfg, dict):
                    cfg = {}
                if not isinstance(val_obj, dict):
                    val_obj = {}
                value = _extract_value(val_obj)
                wkn = cfg.get("WellKnownName") or ""
                display = cfg.get("DisplayName") or ""
                if wkn and wkn not in device.values:
                    device.values[wkn] = value
                if display and display not in device.display_values:
                    device.display_values[display] = value
                if not device.device_type and cfg.get("DeviceType"):
                    device.device_type = int(cfg["DeviceType"])

    async def _request(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        *,
        methods: tuple[str, ...] = ("POST",),
        dest_options: tuple[bool, ...] = (True, False),
        auth: bool = True,
    ) -> Any:
        last_error: KermiError | None = None
        for with_dest in dest_options:
            for method in methods:
                try:
                    return await self._request_once(
                        endpoint,
                        payload,
                        method=method,
                        with_dest=with_dest,
                        auth=auth,
                    )
                except KermiConnectionError as exc:
                    last_error = exc
                    if not any(f"HTTP {status}" in str(exc) for status in _RETRYABLE_STATUS):
                        raise
                    _LOGGER.debug("%s %s dest=%s failed: %s", method, endpoint, with_dest, exc)
        if last_error:
            raise last_error
        raise KermiConnectionError(f"{endpoint} failed")

    async def _request_once(
        self,
        endpoint: str,
        payload: dict[str, Any] | None,
        *,
        method: str,
        with_dest: bool,
        auth: bool = True,
        retry: bool = True,
    ) -> Any:
        url = f"{self._base}/{endpoint}/{DESTINATION_ID}" if with_dest else f"{self._base}/{endpoint}"
        session = self._ensure_session()
        headers = {"Accept": "application/json"}
        try:
            if method == "GET":
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    return await self._parse_response(
                        resp, endpoint, payload, method, with_dest, auth, retry
                    )
            async with session.post(
                url,
                json=payload if payload is not None else {},
                headers={**headers, "Content-Type": "application/json"},
                allow_redirects=False,
            ) as resp:
                return await self._parse_response(
                    resp, endpoint, payload, method, with_dest, auth, retry
                )
        except (ClientError, TimeoutError, OSError) as exc:
            raise KermiConnectionError(str(exc)) from exc

    async def _parse_response(
        self,
        resp: Any,
        endpoint: str,
        payload: dict[str, Any] | None,
        method: str,
        with_dest: bool,
        auth: bool,
        retry: bool,
    ) -> Any:
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            if retry and auth:
                await self.async_login()
                return await self._request_once(
                    endpoint,
                    payload,
                    method=method,
                    with_dest=with_dest,
                    auth=auth,
                    retry=False,
                )
            raise KermiAuthError("Session expired")
        if resp.status == 401:
            raise KermiAuthError("Unauthorized")
        if resp.status >= 400:
            allow = resp.headers.get("Allow")
            extra = f" Allow={allow}" if allow else ""
            raise KermiConnectionError(f"{method} {resp.url} HTTP {resp.status}{extra}")
        body = await resp.json(content_type=None)
        if not isinstance(body, dict):
            return body
        if "isValid" in body:
            return body
        status = body.get("StatusCode", 0)
        if status:
            text = body.get("DisplayText") or body.get("DetailedText") or f"API error {status}"
            raise KermiError(text)
        if "ResponseData" in body:
            return body.get("ResponseData")
        return body
