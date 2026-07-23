"""Raylogic MOD4U integration - RE8-style config-entry architecture.

MOD2U se generalize kiya gaya: 2 ki jagah 4 physical channels, 2 PAIRS
(Pair 1 = channel_start/+1, Pair 2 = channel_start+2/+3). Relay/Dimmer/Fan
har channel independently set ho sakta hai, lekin Curtain aur CTC dono
PAIRED modes hain - jis pair ka koi ek channel Curtain ya CTC banaya jaaye,
wo poora pair (dono physical channels) ek hi logical entity ke andar
consume ho jaata hai (bilkul MOD2U ke CTC jaisa - yahan Curtain bhi wahi
rule follow karta hai)."""
from __future__ import annotations
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DEFAULT_PORT, DOMAIN, PLATFORMS,
    LEGACY_DEFAULT_AREA, DEFAULT_CHANNEL_COUNT,
    CH_TYPE_CTC, CH_TYPE_CURTAIN, CH_TYPE_RELAY,
    CTC_MODE_SINGLE,
)
from .protocol import RaylogicMod4uDevice

_LOGGER = logging.getLogger(__name__)

CONF_LEGACY_AREA = "legacy_area"
CONF_LEGACY_CHANNEL_COUNT = "legacy_channel_count"
CONF_CHANNEL_START = "channel_start"
CONF_CH1_TYPE = "channel_1_type"
CONF_CH2_TYPE = "channel_2_type"
CONF_CH3_TYPE = "channel_3_type"
CONF_CH4_TYPE = "channel_4_type"
CONF_CH1_CTC_MODE = "channel_1_ctc_mode"
CONF_CH2_CTC_MODE = "channel_2_ctc_mode"
CONF_CH3_CTC_MODE = "channel_3_ctc_mode"
CONF_CH4_CTC_MODE = "channel_4_ctc_mode"

# Pair layout: (type_conf_key_lo, type_conf_key_hi, ctc_mode_key_lo, ctc_mode_key_hi)
_PAIR_CONF_KEYS = (
    (CONF_CH1_TYPE, CONF_CH2_TYPE, CONF_CH1_CTC_MODE, CONF_CH2_CTC_MODE),
    (CONF_CH3_TYPE, CONF_CH4_TYPE, CONF_CH3_CTC_MODE, CONF_CH4_CTC_MODE),
)


def _resolve_channel_types(conf: dict, channel_start: int) -> tuple[dict[int, str], dict[int, str]]:
    """Config (channel_1_type..channel_4_type) ko physical channel_types /
    channel_ctc_modes dicts mein resolve karo, 2 pairs ke liye.

    Har pair (lo, hi) ke liye:
      - agar lo ka type 'ctc' ya 'curtain' hai -> sirf lo entry banti hai
        (paired entity), hi ko IGNORE kiya jaata hai (uski apni entity
        nahi banti - warna dono channels ke liye do alag entity bante jo
        ek hi physical hardware par conflict karte, jaisa MOD2U CTC mein
        already tha).
      - warna agar hi ka type 'ctc' ya 'curtain' hai -> sirf hi entry
        (same reason, symmetric case).
      - warna (dono normal: relay/dimmer/fan) -> dono independently apni
        apni entity paate hain, jaisa pehle tha.
    """
    channel_types: dict[int, str] = {}
    channel_ctc_modes: dict[int, str] = {}

    for pair_index, (lo_key, hi_key, lo_ctc_key, hi_ctc_key) in enumerate(_PAIR_CONF_KEYS):
        phys_lo = channel_start + pair_index * 2
        phys_hi = phys_lo + 1
        type_lo = conf.get(lo_key, CH_TYPE_RELAY)
        type_hi = conf.get(hi_key, CH_TYPE_RELAY)

        if type_lo in (CH_TYPE_CTC, CH_TYPE_CURTAIN):
            channel_types[phys_lo] = type_lo
            if type_lo == CH_TYPE_CTC:
                channel_ctc_modes[phys_lo] = conf.get(lo_ctc_key, CTC_MODE_SINGLE)
        elif type_hi in (CH_TYPE_CTC, CH_TYPE_CURTAIN):
            channel_types[phys_hi] = type_hi
            if type_hi == CH_TYPE_CTC:
                channel_ctc_modes[phys_hi] = conf.get(hi_ctc_key, CTC_MODE_SINGLE)
        else:
            channel_types[phys_lo] = type_lo
            channel_types[phys_hi] = type_hi

    return channel_types, channel_ctc_modes


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # options (naye "Configure" button se) data (initial add se) ke upar
    # priority lete hain - taaki channel type badalne ke baad delete+re-add
    # kiye bina bhi naya config turant effect kare.
    conf = {**entry.data, **entry.options}

    host = conf[CONF_HOST]
    port = conf.get(CONF_PORT, DEFAULT_PORT)
    # 0 = relay-only auto/learn mode - Area manually diya gaya nahi hai
    legacy_area = conf.get(CONF_LEGACY_AREA, LEGACY_DEFAULT_AREA)
    legacy_channel_count = conf.get(CONF_LEGACY_CHANNEL_COUNT, DEFAULT_CHANNEL_COUNT)
    # Kai installations mein channel numbering 1 se shuru nahi hoti (Area ke
    # andar globally assign hoti hai) - is device ka pehla channel number.
    channel_start = conf.get(CONF_CHANNEL_START, 1)
    # Raylogic GO app mein jo type set kiya gaya hai (relay/dimmer/fan/
    # curtain/ctc) - keys ab actual physical channel numbers hain
    # (channel_start se shuru), 2 pairs ke liye resolve kiya jaata hai.
    channel_types, channel_ctc_modes = _resolve_channel_types(conf, channel_start)

    device = RaylogicMod4uDevice(
        ip=host, port=port,
        legacy_area=legacy_area,
        legacy_channel_count=legacy_channel_count,
        channel_start=channel_start,
        channel_types=channel_types,
        channel_ctc_modes=channel_ctc_modes,
        state_callback=lambda ip, ch, state: _handle_state_update(
            hass, entry.entry_id, ip, ch, state
        ),
    )

    connected = await device.connect()
    if not connected:
        # BUG FIX: pehle yahan `return False` tha - HA isse entry ko seedha
        # "setup failed" maan leta tha, proper exponential-backoff retry
        # nahi hoti thi. ConfigEntryNotReady raise karne se HA khud isse
        # thodi thodi der mein retry karta rehta hai (jaisa device boot ke
        # time thoda der se network par aaye) - startup "stuck" jaisa feel
        # nahi hota, aur baad mein device aane par integration khud theek
        # ho jaati hai, manual reload ki zaroorat nahi padti.
        raise ConfigEntryNotReady(
            f"Could not connect to Raylogic MOD4U at {host}:{port}"
        )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = device

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options flow se save hote hi poora entry reload karo."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    device: RaylogicMod4uDevice = hass.data[DOMAIN].get(entry.entry_id)
    if device:
        await device.disconnect()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _handle_state_update(hass, entry_id, ip, ch, state):
    if "available" in state:
        hass.bus.async_fire(
            f"{DOMAIN}_available",
            {"entry_id": entry_id, "available": state["available"]},
        )
        return
    hass.bus.async_fire(
        f"{DOMAIN}_state_update",
        {"entry_id": entry_id, "ip": ip, "channel": ch, "state": state},
    )
    hass.bus.async_fire(
        f"{DOMAIN}_available",
        {"entry_id": entry_id, "available": True},
    )
