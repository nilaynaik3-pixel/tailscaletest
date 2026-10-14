"""Friends Connection Test.

A throwaway helper: checks that two Home Assistants can reach each other
over Tailscale, before installing Workout Tracker's Friends feature.

- Answers GET /api/friends_connection_test/ping (no login), so a friend's
  Home Assistant can see this one is there.
- Action friends_connection_test.check: tries an address and reports the
  result as a notification (and as the action's response).
- On setup it checks its own Tailscale address.

Delete it when you're done: Settings > Devices & services > Friends
Connection Test > Delete, then remove the folder and restart.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time

import voluptuous as vol
from aiohttp import web

from homeassistant.components import persistent_notification
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

DOMAIN = "friends_connection_test"
PING = "/api/friends_connection_test/ping"
NOTE_ID = "friends_connection_test"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

HINTS_FRIEND = (
    "\n\nThings to check:\n"
    "- Tailscale add-on running on both Home Assistants.\n"
    "- **Userspace networking off** in *your* Tailscale add-on (Configuration tab), then restart the add-on.\n"
    "- In the Tailscale admin console your friend has **shared** their Home Assistant machine with you "
    "(and you yours with them: sharing only works one way).\n"
    "- The address is right (the friend's Home Assistant machine in the Tailscale app), port 8123."
)
HINTS_SELF = (
    "\n\nThings to check:\n"
    "- **Userspace networking off** in the Tailscale add-on (Configuration tab), then restart the add-on.\n"
    "- The address is this Home Assistant's Tailscale address (Tailscale app > Machines)."
)


class PingView(HomeAssistantView):
    url = PING
    name = "api:friends_connection_test:ping"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request):
        return web.json_response({"app": DOMAIN, "name": self.hass.config.location_name})


async def _tailscale_address(hass: HomeAssistant) -> str:
    """This Home Assistant's Tailscale address, if it can see a Tailscale interface."""
    try:
        from homeassistant.components import network
        adapters = await network.async_get_adapters(hass)
    except Exception:  # noqa: BLE001
        return ""
    cgnat = ipaddress.ip_network("100.64.0.0/10")
    port = getattr(hass.http, "server_port", None) or 8123
    for a in adapters:
        for ip in a.get("ipv4") or []:
            try:
                if ipaddress.ip_address(ip["address"]) in cgnat:
                    return f"http://{ip['address']}:{port}"
            except ValueError:
                continue
    return ""


async def _get(hass: HomeAssistant, url: str):
    """(status, json or None, milliseconds); status 0 = no answer."""
    session = async_get_clientsession(hass, verify_ssl=False)
    t0 = time.monotonic()
    try:
        async with asyncio.timeout(10):
            async with session.get(url) as r:
                try:
                    data = await r.json(content_type=None)
                except ValueError:
                    data = None
                return r.status, data, round((time.monotonic() - t0) * 1000)
    except Exception as err:  # noqa: BLE001  (timeout, refused, no route: all "no answer")
        _LOGGER.info("friends_connection_test: %s: %s", url, err.__class__.__name__)
        return 0, {"error": f"{err.__class__.__name__}: {err}"}, round((time.monotonic() - t0) * 1000)


def _normalise(address: str) -> str:
    url = address.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    if url and ":" not in url.split("//", 1)[1]:
        url += ":8123"
    return url


async def _check(hass: HomeAssistant, address: str) -> dict:
    mine = not address.strip()
    own = await _tailscale_address(hass)
    url = _normalise(address) if not mine else own
    result = {"address": url, "own_tailscale_address": own or None, "checked_own": mine}
    if not url:
        result.update(ok=False, summary="No Tailscale address found on this Home Assistant.",
                      detail="Home Assistant can't see a Tailscale network interface." + HINTS_SELF)
        return result
    status, data, ms = await _get(hass, url + "/manifest.json")
    is_ha = status == 200 and isinstance(data, dict) and (
        "Home Assistant" in str(data.get("name", "")) or "start_url" in data)
    result["home_assistant"] = is_ha
    if status == 0:
        result.update(ok=False, summary=f"No answer from {url} after {ms} ms.",
                      detail=f"Error: {(data or {}).get('error', 'unknown')}" + (HINTS_SELF if mine else HINTS_FRIEND))
        return result
    if not is_ha:
        result.update(ok=False, summary=f"{url} answered (HTTP {status}) but it isn't Home Assistant.",
                      detail="Check the address and port.")
        return result
    p_status, p_data, _ = await _get(hass, url + PING)
    has_test = p_status == 200 and isinstance(p_data, dict) and p_data.get("app") == DOMAIN
    result["has_connection_test"] = has_test
    name = (p_data or {}).get("name") if has_test else None
    label = f' "{name}"' if name else ""
    result.update(ok=True, summary=f"Reached Home Assistant{label} at {url} in {ms} ms.",
                  detail="Tailscale works in this direction."
                  + ("" if has_test or mine else
                     "\n\nTheir Home Assistant doesn't have this connection test installed, which is fine. "
                     "To test the other direction, they install it and check your address."))
    return result


def _notify(hass: HomeAssistant, res: dict) -> None:
    icon = "✅" if res["ok"] else "❌"
    own = res.get("own_tailscale_address")
    msg = f"{icon} **{res['summary']}**\n\n{res['detail']}"
    msg += f"\n\nYour own Tailscale address (give this to your friend): **{own}**" if own else \
        "\n\nNo Tailscale address found on this Home Assistant (is Userspace networking off?)."
    persistent_notification.async_create(hass, msg, title="Friends Connection Test", notification_id=NOTE_ID)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not hass.data.get(DOMAIN):
        hass.http.register_view(PingView(hass))
        hass.data[DOMAIN] = True

    async def handle(call: ServiceCall) -> ServiceResponse:
        res = await _check(hass, str(call.data.get("address") or ""))
        _notify(hass, res)
        return res

    hass.services.async_register(
        DOMAIN, "check", handle,
        schema=vol.Schema({vol.Optional("address", default=""): cv.string}),
        supports_response=SupportsResponse.OPTIONAL)

    async def first_check():
        _notify(hass, await _check(hass, ""))

    hass.async_create_task(first_check())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.services.async_remove(DOMAIN, "check")
    persistent_notification.async_dismiss(hass, NOTE_ID)
    return True
