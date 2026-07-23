"""Raylogic MOD4U curtain platform.

Model_Number_Mod2u.txt capture se CONFIRMED, lekin sirf PAIR 1 ke liye
(curtain ek alag frame-shape use karta hai, formula se derive nahi hua,
aur CTC ki tarah ye bhi ek PAIRED mode hai - jis pair ka ek channel
curtain banaya jaaye, wahi pura pair ek logical curtain entity ban jaata
hai). Pair 2 (channel_start+2/+3) par curtain ho to Raylogic GO app se ek
baar open/close/stop karke raylogic_mod4u ke debug log se *AR=/*AZ= line
share karo, taaki wo bhi add ho sake.

CTC (Double/Single Driver CCT) ab supported hai, lekin ek `light` entity
ke taur par (Colour Temperature control) - dekho light.py -
RaylogicMod4uCtcLight. Yahan cover.py mein sirf isliye reference hai taaki
CTC-type channel ke liye galti se doosri cover entity na ban jaaye.
"""
from __future__ import annotations
import logging

from homeassistant.components.cover import CoverEntity, CoverEntityFeature, CoverDeviceClass
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, CH_TYPE_CURTAIN, CH_TYPE_CTC, DEVICE_MODEL_NAME, DEVICE_MODEL_DESC
from .protocol import RaylogicMod4uDevice

_LOGGER = logging.getLogger(__name__)

# Pair 0 (Pair 1 = channel_start/+1) hi curtain ke liye confirmed hai
# abhi tak - dekho const.py CURTAIN_PAIR_COMMANDS.
_CONFIRMED_CURTAIN_PAIR_INDEX = 0


async def async_setup_entry(hass, entry, async_add_entities):
    device: RaylogicMod4uDevice = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for ch_num, state in device.channel_states.items():
        if state.get("type") == CH_TYPE_CURTAIN:
            pair_index = device.pair_index_for_channel(ch_num)
            if pair_index == _CONFIRMED_CURTAIN_PAIR_INDEX:
                entities.append(RaylogicMod4uCover(hass, entry, device, ch_num, state))
            else:
                _LOGGER.warning(
                    "Raylogic MOD4U %s: channel %d curtain type hai "
                    "(Pair %d), lekin curtain bytes sirf Pair %d ke liye "
                    "confirmed hain - entity nahi banai. App se ek baar "
                    "open/close karke log share karo.",
                    device.ip, ch_num, pair_index + 1,
                    _CONFIRMED_CURTAIN_PAIR_INDEX + 1,
                )
        elif state.get("type") == CH_TYPE_CTC:
            _LOGGER.debug(
                "Raylogic MOD4U %s: channel %d CTC type hai - is platform "
                "(cover) mein entity nahi banti, dekho 'light' platform "
                "(RaylogicMod4uCtcLight).", device.ip, ch_num,
            )
    if entities:
        _LOGGER.info("Setting up %d MOD4U curtain channel(s) on %s", len(entities), device.ip)
        async_add_entities(entities)


class RaylogicMod4uCover(CoverEntity):
    _attr_has_entity_name = False
    _attr_device_class = CoverDeviceClass.CURTAIN
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, hass, entry, device: RaylogicMod4uDevice, ch_num, initial_state):
        self._hass = hass
        self._entry = entry
        self._device = device
        self._ch_num = ch_num
        suffix = device.ip_suffix
        area = initial_state.get("area", 0)
        self._attr_unique_id = f"{device.node_id or device.ip}_mod4u_ch{ch_num}"
        self._attr_name = f"mod4u_{suffix}_area{area}_ch{ch_num}_curtain"
        self._is_closed = not initial_state.get("on", False)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.node_id or self._device.ip)},
            name=f"Raylogic MOD4U ({self._device.ip})",
            manufacturer="Raylogic",
            model=f"{DEVICE_MODEL_NAME} - {DEVICE_MODEL_DESC}",
            sw_version=self._device.fw_version,
        )

    @property
    def available(self):
        return self._device.is_connected

    @property
    def is_closed(self):
        return self._is_closed

    async def async_open_cover(self, **kwargs):
        await self._device.set_cover(self._ch_num, "open")
        self._is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs):
        await self._device.set_cover(self._ch_num, "close")
        self._is_closed = True
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs):
        await self._device.set_cover(self._ch_num, "stop")

    async def async_added_to_hass(self):
        self.async_on_remove(
            self._hass.bus.async_listen(f"{DOMAIN}_state_update", self._on_update)
        )
        self.async_on_remove(
            self._hass.bus.async_listen(f"{DOMAIN}_available", self._on_available)
        )

    @callback
    def _on_update(self, event):
        d = event.data
        if d.get("entry_id") == self._entry.entry_id and d.get("channel") == self._ch_num:
            s = d.get("state", {})
            if "on" in s:
                self._is_closed = not bool(s["on"])
            self.async_write_ha_state()

    @callback
    def _on_available(self, event):
        if event.data.get("entry_id") == self._entry.entry_id:
            self.async_write_ha_state()
