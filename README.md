# Raylogic MOD4U - Home Assistant Integration

RE8-style config-flow architecture for the Raylogic MOD4U 4-channel universal
module (Relay / Dimmer / Fan / Curtain / CTC per channel).

MOD4U ke 4 physical channels 2 **PAIRS** mein hote hain:

- **Pair 1** = Channel 1 + Channel 2
- **Pair 2** = Channel 3 + Channel 4

Relay, Dimmer, aur Fan har channel par **independently** set ho sakte hain.
Curtain aur CTC (colour-temperature) dono **paired** modes hain - jis pair
ka koi ek channel Curtain ya CTC banaya jaata hai, wahi pura pair (dono
physical channels) ek hi logical entity ke andar internally consume ho
jaata hai (2 alag entity nahi bantin).

## Setup

1. Copy `custom_components/raylogic_mod4u` into your HA `config/custom_components/`.
2. Restart Home Assistant.
3. Settings -> Devices & Services -> Add Integration -> "Raylogic MOD4U".
4. Fill in:
   - **IP Address** / **Port** (default 5550).
   - **Area** - the Area number shown on your device's Mod Settings screen
     (e.g. 12, or 16 for a CTC pair). Use `0` only if ALL 4 channels are
     Relay - HA will then learn the Area itself the first time you toggle
     each channel from the Raylogic GO app or a physical switch, instead of
     you typing it.
   - **Channel 1-4 Type** - pick whatever you set on that channel in the
     Raylogic GO app's "Select Type" screen: `relay`, `dimmer`, `fan`,
     `curtain`, or `ctc`. The device does not report its own channel type
     over the network, so this has to be told to HA once.
   - **CTC / Curtain (paired types)**: setting **Channel 1 Type** (or
     **Channel 3 Type**) to `ctc` or `curtain` automatically makes HA
     ignore **Channel 2 Type** (or **Channel 4 Type**) for that pair - you
     get one entity for the whole pair, not two conflicting ones. Also
     pick the **CTC Driver Mode** for whichever channel you set to `ctc`,
     matching the Double Driver / Single Driver checkbox on the app's Mod
     Settings screen for that pair - Pair 1 and Pair 2 can use different
     Driver Modes independently.

## What's confirmed vs. not

MOD4U shares the exact same wire protocol as MOD2U (`*AR=`/`*AZ=` frame
shapes), just with 4 channels / 2 pairs instead of 2 channels / 1 pair, so
everything captured on MOD2U (`Model_Number_Mod2u.txt` vendor capture)
carries over directly:

| Type     | Status                                                        |
|----------|----------------------------------------------------------------|
| Relay    | Fully confirmed, all 4 channels, any Area.                    |
| Fan      | Fully confirmed (off + 4 speeds), all 4 channels, any Area.    |
| Dimmer   | Confirmed on/off + endpoints; brightness curve is a linear approximation between the two confirmed endpoints (0x01=full, 0xFF=off). All 4 channels. |
| Curtain  | Confirmed for **Pair 1 (Channel 1+2) only** (open/close/stop). Pair 2 (Channel 3+4) curtain bytes were never captured. |
| CTC (Single Driver) | Brightness sub-command confirmed (same curve as Dimmer). Colour-temperature sub-command: only 14 discrete captured points - implemented as a linear approximation between the two confirmed endpoints, same approach as Dimmer. Works correctly on **either pair** (Pair 1 or Pair 2, or both at once) - the integration derives each CTC entity's own physical channel pair rather than assuming it's always Pair 1. Which physical end is "warm" vs "cool" was **not** recorded in the capture - if it comes out backwards on your bulb, that's a one-line const.py fix (swap `CTC_SINGLE_CT_MIN_LEVEL`/`MAX_LEVEL`), not a re-engineer. |
| CTC (Double Driver) | Only pure brightness-only and pure colour-only sweeps were captured (not a combined change) - the warm/cool formula is derived to satisfy both sweeps exactly, but is **not directly captured** for combined brightness+colour changes. Should work, but test more carefully than Single Driver. **Limitation**: the `*AZ=` double-driver frame only carries the Area byte, not a real per-pair channel number - so two Double Driver CTC pairs on the *same* Area can't be told apart by software. Use different Areas for two Double Driver pairs on one module, or use Single Driver mode (which does carry a real channel number and is correctly disambiguated per-pair). |

If you wire a curtain to Pair 2, want a tighter dimmer curve, or can
capture a combined brightness+colour CTC change (Double Driver), toggle the
control once from the Raylogic GO app while the HA log is on `debug` for
`custom_components.raylogic_mod4u`, and share the resulting `*AR=`/`*AZ=`
line so it can be tightened up further.

## Learn mode (Relay only, Area = 0)

If Area is left at `0` and a channel is Relay, HA passively listens for the
`*AR=` frame the module broadcasts when you toggle that channel from the
app or a physical switch, learns its Area, and creates the entity on the
fly (no restart needed). This does **not** work for Dimmer/Fan/Curtain/CTC -
those need Area set manually, since their "on" frame can't be reliably
told apart from a Relay frame just by listening.

## Differences from Raylogic MOD2U

This integration is generalized from the `raylogic_mod2u` integration
(same author, same protocol). Two things were fixed while generalizing to
4 channels / 2 pairs:

1. **CTC pair derivation bug**: MOD2U's code always assumed a CTC
   channel's pair was `(channel_start, channel_start + 1)` - fine on
   MOD2U since there's only ever one pair, but on MOD4U this would have
   silently broken a CTC pair configured on Pair 2 (Channel 3-4), using
   the wrong physical channels. MOD4U now derives each CTC entity's pair
   from its own configured channel position.
2. **CTC same-Area disambiguation**: if two Single Driver CTC pairs are
   configured on the same Area, MOD4U now matches incoming frames to the
   correct pair using the real channel number carried in the frame,
   instead of returning whichever CTC channel was found first.

Curtain was also generalized from a single hardcoded "Channel 1 only"
check to a proper per-pair check, matching how CTC already worked.
