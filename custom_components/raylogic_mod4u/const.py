"""Constants for the Raylogic MOD4U integration.

MOD4U bhi MOD2U jaisa hi "universal module" hai (same Raylogic GO app, same
Select Type screen) - farak sirf itna hai ki MOD4U mein 2 ki jagah 4
physical channels hote hain, jo 2 PAIRS mein group hote hain:
  Pair 1 = channel_start + 0, channel_start + 1   (jaise ch1, ch2)
  Pair 2 = channel_start + 2, channel_start + 3   (jaise ch3, ch4)
Har channel ko independently Relay / Dimmer / Fan banaya ja sakta hai, LEKIN
Curtain aur CTC dono "paired" modes hain - jab kisi pair ka ek channel
Curtain ya CTC banaya jaata hai, wahi pura pair (dono physical channels)
us EK logical entity ke andar internally consume ho jaata hai (bilkul jaisa
MOD2U mein CTC ke liye tha - yahan Curtain bhi wahi rule follow karta hai,
jaisa user ne confirm kiya).

Is file mein 2 tarah ke values hain:
  1. CONFIRMED  - MOD2U capture se already verify ho chuka hai (Relay/
     Dimmer/Fan/CTC-pair1 format MOD4U ke liye bhi identical hai, kyunki
     wire-protocol level pe MOD4U bhi wahi *AR=/*AZ= frame shape use karta
     hai, sirf zyada channels/pairs).
  2. PLACEHOLDER / TODO - Pair 2 (channel 3-4) ke Curtain literal bytes,
     aur MOD4U ka apna BR40 code, abhi tak capture nahi hue. Jaha
     "TODO CAPTURE" likha hai, wahan real value pata chalte hi yahin update
     karna hai. Tab tak fallback/warning logic (protocol.py mein) safe
     defaults use karta hai.
"""

DOMAIN = "raylogic_mod4u"

# Network -------------------------------------------------------------- #
DEFAULT_PORT = 5550
CONNECT_TIMEOUT = 5
RECONNECT_DELAY = 30

# ------------------------------------------------------------------ #
# BR40 identification
#
# H81/RE16/FN4/RE8 (Din-Re8 repo) sabka apna unique byte[1] BR40 code hai,
# jo *KA= push line ke andar byte[7] par milta hai (raylogic/protocol.py
# ka _extract_br40_code_from_ka dekho). MOD4U ka apna BR40 code ABHI TAK
# CONFIRM NAHI HUA (MOD2U ka bhi nahi hua tha) - koi BR40 query/response
# capture nahi tha, sirf direct *AR= relay commands the.
#
# TODO CAPTURE: Jab bhi MOD4U HA se connect ho, protocol.py raw *KA= line
# ko INFO level par log karega - us log line ka "byte[7]" (ya poora hex)
# humein bhejo, hum BR40_CODE_MOD4U yahan fill kar denge. Tab tak
# BR40_CODE_MOD4U = None rehta hai aur integration "legacy mode" (static
# 4-channel, jaisa MOD2U bhi legacy mode mein karta hai) mein fallback
# karta hai.
# ------------------------------------------------------------------ #
BR40_CODE_MOD4U = None  # TODO CAPTURE - fill after first real *KA= log

DEVICE_MODEL_NAME = "MOD4U"
DEVICE_MODEL_DESC = "Universal 4-Channel Module (Dimmer/Fan/Curtain/Relay/CTC)"

# ------------------------------------------------------------------ #
# Area
# MOD2U capture se confirm hua: Area byte = seedha area number ka hex hai
# (Area 12 -> 0x0C). MOD4U bhi wahi Area scheme use karta hai (1-16).
# ------------------------------------------------------------------ #
AREA_MIN = 1
AREA_MAX = 16
LEGACY_DEFAULT_AREA = 0x0C  # 12 - sirf tab use hota hai jab BR40 na mile aur
                             # user ne config mein area na diya ho

# ------------------------------------------------------------------ #
# Command bytes - CONFIRMED (Docklight capture, MOD2U se, same wire
# protocol MOD4U ke liye bhi)
#   <ID>,<Seq>,*AR=<AddrHigh:00><Cmd:1A><Area><Level><Channel>
#   Relay: Level 01=OFF, 02=ON
# ------------------------------------------------------------------ #
CMD_ADDR_HIGH = "00"
CMD_CHANNEL_DIRECT = "1A"
RELAY_LEVEL_ON = "02"
RELAY_LEVEL_OFF = "01"

# ------------------------------------------------------------------ #
# Dimmer - CONFIRMED (Model_Number_Mod2u.txt, vendor capture, Area 12):
#   Ch1 On :  *AR=001A0C0101  -> level=01 (full/on)
#   Ch1 Off:  *AR=001A0CFF01  -> level=FF (off)
#   Ch1 dimming ramp goes FF -> ... -> 69 as brightness increases
#   Ch2 same pattern with channel byte = 02
# Same frame shape as Relay (00 1A <area> <level> <channel>), only the
# level byte meaning is different: 0x01 = full brightness, 0xFF = off,
# values in between are a proprietary dim curve. No exact 256-step table
# was captured, so brightness is mapped linearly between the two
# confirmed endpoints (good enough approximation; refine if a fuller
# capture turns up). Frame shape is per-channel (channel byte = the real
# physical channel number), so this scales to all 4 MOD4U channels
# unchanged - no MOD4U-specific capture needed.
# ------------------------------------------------------------------ #
DIMMER_LEVEL_ON = 0x01
DIMMER_LEVEL_OFF = 0xFF

# ------------------------------------------------------------------ #
# CTC (Colour Temperature Control / tunable white) - CONFIRMED
# (Model_Number_Mod2u.txt capture, Area 16, matches the user's own Mod
# Settings screenshot: Channel 1 = CTC, "Single Driver" checked).
#
# The Raylogic GO app supports TWO CTC sub-modes, each with its own wire
# format - which one a module uses is a config choice (the Double
# Driver / Single Driver checkboxes in the app), not something the
# device reports on its own, so it's selected in this integration's
# config too (see config_flow.py CTC_MODE_OPTIONS). MOD4U ke liye is
# sub-mode ko HAR PAIR ke liye ALAG se choose kiya ja sakta hai (Pair 1
# aur Pair 2 dono independently single ya double ho sakte hain).
#
# 1) SINGLE DRIVER (CW/WW, one physical channel-PAIR - confirmed by the
#    user: configuring a CTC light in the Raylogic GO app actually
#    consumes TWO real physical channels, e.g. channel 3 + channel 4,
#    exactly like any other 2-channel allocation on this device) -
#    identical frame shape to Relay/Dimmer/Fan (00 1A <area> <level>
#    <channel>), and the "channel" byte here IS the real physical
#    channel number of the pair, same as everywhere else in this
#    protocol - NOT a fixed 0x01/0x02 sub-signal id as first assumed.
#    Within the pair:
#      the LOWER physical channel number  -> colour temperature,
#        level 0x0B..0xFF across the 14 captured points (monotonic) -
#        linear approximation between the two confirmed endpoints,
#        same "good enough" approach already used for the Dimmer
#        brightness curve above. Which physical end (warm/cool) 0x0B
#        vs 0xFF corresponds to was NOT recorded in the capture (only
#        consecutive level values, no colour reference) - if warm/cool
#        comes out reversed in practice, just swap
#        CTC_SINGLE_CT_MIN_LEVEL/MAX_LEVEL below.
#      the HIGHER physical channel number -> brightness, level
#        0x01=full .. 0xFF=off (same curve/formula as Dimmer above,
#        reused as-is).
#    This "lower=CT, higher=brightness" rule applies to WHICHEVER pair
#    the CTC channel is in (Pair 1 = channel_start/channel_start+1, or
#    Pair 2 = channel_start+2/channel_start+3) - protocol.py derives the
#    pair from the configured CTC channel's own position, not a fixed
#    channel_start/channel_start+1 assumption (that was a MOD2U-only
#    shortcut since MOD2U only ever HAD one pair).
#
# 2) DOUBLE DRIVER (separate warm+cool physical channels, combined into
#    one *AZ= frame instead of *AR=):
#      Frame (7 bytes after *AZ=): <area><01><warm><02><cool><64><pct>
#      warm+cool always summed to 0x100 (256) in every captured colour-
#      temperature-only sweep (fixed 100% brightness); a separate
#      brightness-only sweep (fixed colour) varied that same "cool"
#      byte position from 0xFF(off) down to 0x01(full) as brightness
#      rose 0->100%. Both are consistent with a normal dual-channel
#      cross-fade driver where each channel follows the same
#      0x01=full/0xFF=off convention used everywhere else in this
#      protocol, scaled by both colour-temp position AND overall
#      brightness together. `pct` (last byte) is brightness 0-100
#      (0x00-0x64) and moved in lockstep with the scaled channel bytes
#      in every sample. Only PURE colour-only and PURE brightness-only
#      sweeps were captured (not an arbitrary combined change) - the
#      formula in protocol.py is derived to satisfy both captured
#      sweeps exactly, but a combined brightness+colour capture would
#      help confirm it fully.
#      NOTE (MOD4U-specific limitation): the *AZ= double-driver frame
#      only carries <area>, not a real per-channel/per-pair byte (the
#      "01"/"02" in the frame are fixed slot markers, not channel
#      numbers) - so if you configure TWO double-driver CTC pairs on
#      the SAME Area, the module's frames can't be told apart in
#      software. Use different Areas for two double-driver CTC pairs,
#      or use single-driver mode (which DOES carry a real channel
#      number and is correctly disambiguated per-pair).
# ------------------------------------------------------------------ #
CTC_MODE_SINGLE = "single"
CTC_MODE_DOUBLE = "double"

CTC_SINGLE_BRIGHTNESS_ON = DIMMER_LEVEL_ON      # 0x01, same curve as Dimmer
CTC_SINGLE_BRIGHTNESS_OFF = DIMMER_LEVEL_OFF    # 0xFF
CTC_SINGLE_CT_MIN_LEVEL = 0x0B   # confirmed lowest captured level
CTC_SINGLE_CT_MAX_LEVEL = 0xFF   # confirmed highest captured level

CTC_DOUBLE_CONST_BYTE = 0x64     # constant byte seen in every *AZ= sample

CTC_MIN_KELVIN = 2700   # warmest end of the HA colour-temp slider
CTC_MAX_KELVIN = 6500   # coolest end of the HA colour-temp slider
CTC_DEFAULT_KELVIN = 4000

# ------------------------------------------------------------------ #
# Fan - CONFIRMED (Model_Number_Mod2u.txt, Area 12):
#   Off:     *AR=001A0C0101 (ch1) / ...0102 (ch2) -> level=01
#   Speed 1: level=02   Speed 2: level=03
#   Speed 3: level=04   Speed 4: level=05
# Identical scheme to the Din-Re8 FN4 fan. Per-channel frame (channel
# byte = real physical channel), so this scales to all 4 MOD4U channels
# unchanged.
# ------------------------------------------------------------------ #
FAN_LEVEL_OFF = 0x01
FAN_SPEEDS = {0: 0x01, 25: 0x02, 50: 0x03, 75: 0x04, 100: 0x05}

# ------------------------------------------------------------------ #
# Curtain - CONFIRMED for PAIR 1 only (Model_Number_Mod2u.txt, Area 12,
# captured as "Channel 1" on a MOD2U - jo asal mein us device ka poora
# (aur sirf) pair tha). Curtain uses a DIFFERENT frame shape than Relay/
# Dimmer/Fan (cmd byte 0x27/0x26 instead of 0x1A, and no visible
# per-channel/per-pair byte in the captured samples) - so these are
# stored as exact literal command strings rather than derived from a
# formula.
#
# MOD4U ke 2 pairs hote hain (Pair 1 = channel_start/+1, Pair 2 =
# channel_start+2/+3) - is confirmed literal Pair 1 ke liye hi hai. Pair
# 2 curtain bytes NOT captured - agar Pair 2 (channel 3-4) par curtain
# wire karo, toggle it once from the Raylogic GO app while watching the
# HA log (raylogic_mod4u debug log) and share the *AR=/*AZ= line so it
# can be added (CURTAIN_PAIR2_OPEN/CLOSE/STOP below).
# ------------------------------------------------------------------ #
CURTAIN_PAIR1_OPEN = "0027010105"
CURTAIN_PAIR1_CLOSE = "0027010205"
CURTAIN_PAIR1_STOP = "0026010000"

# TODO CAPTURE: Pair 2 (channel_start+2 / channel_start+3) curtain bytes.
CURTAIN_PAIR2_OPEN = None
CURTAIN_PAIR2_CLOSE = None
CURTAIN_PAIR2_STOP = None

# pair_index (0=Pair1/ch1-2, 1=Pair2/ch3-4) -> {"open":..,"close":..,"stop":..}
CURTAIN_PAIR_COMMANDS: dict[int, dict[str, str | None]] = {
    0: {"open": CURTAIN_PAIR1_OPEN, "close": CURTAIN_PAIR1_CLOSE, "stop": CURTAIN_PAIR1_STOP},
    1: {"open": CURTAIN_PAIR2_OPEN, "close": CURTAIN_PAIR2_CLOSE, "stop": CURTAIN_PAIR2_STOP},
}

# ------------------------------------------------------------------ #
# +AR40= channel-type map - CONFIRMED (Model_Number_Mod2u.txt).
# This is a CONFIGURATION frame the Raylogic GO app sends to the module
# to SET each channel's mode (relay/dimmer/fan/curtain) - it is not a
# readback/query the module answers on its own, so it can't be used for
# live auto-detection the way RE8's +BR40= can. It's kept here for
# reference/documentation and for a future "set channel mode from HA"
# service, and to interpret the byte if it's ever seen echoed back.
# MOD4U ka apna +AR40= layout (4 channels ke liye ch_count/records kaise
# grow hote hain) capture nahi hua - neeche wala shape MOD2U (2-channel)
# ka hai, sirf reference ke liye.
#   Bytes (12 total, after +AR40=): 01 01 <ch_count> <ch1_type> <ch1_sub>
#   <ch2_type> <ch2_sub> 00 00 00 FF FF
#   ch_type: 00=relay 01=dimmer 02=fan 03=curtain
# ------------------------------------------------------------------ #
AR40_TYPE_RELAY = 0x00
AR40_TYPE_DIMMER = 0x01
AR40_TYPE_FAN = 0x02
AR40_TYPE_CURTAIN = 0x03

# ------------------------------------------------------------------ #
# Channel types (per-channel, as seen in "Select Type" screen)
# Byte-level encoding for these is NOT confirmed for MOD4U yet (MOD2U ka
# bhi nahi tha). Jab tak BR40 record parsing MOD4U ke liye nahi milta,
# har channel "relay" hi treated hota hai (safe/known-good), aur raw
# record bytes log hote hain taaki future mein CHANNEL_TYPE_BYTE_MAP
# bhara ja sake.
# ------------------------------------------------------------------ #
CH_TYPE_DIMMER = "dimmer"
CH_TYPE_FAN = "fan"
CH_TYPE_CURTAIN = "curtain"
CH_TYPE_RELAY = "relay"
CH_TYPE_CTC = "ctc"
CH_TYPE_EMPTY = "empty"

# TODO CAPTURE: <raw type byte value in BR40 record> -> CH_TYPE_*
CHANNEL_TYPE_BYTE_MAP: dict[int, str] = {
    # 0x02: CH_TYPE_RELAY,   # example - fill in once confirmed
}

DEFAULT_CHANNEL_COUNT = 4  # MOD4U default (2 pairs, 4 physical channels)
CHANNELS_PER_PAIR = 2
PAIR_COUNT = DEFAULT_CHANNEL_COUNT // CHANNELS_PER_PAIR  # 2 pairs

PLATFORMS = ["switch", "light", "fan", "cover"]

KEEPALIVE_CMD = "*KA=01"

# ------------------------------------------------------------------ #
# Client sender-ID - CONFIRMED from real Docklight capture (device
# 192.168.1.34:5550, connected DIRECTLY, no TCP-HUB machine in between).
# Real traffic shows TWO different identities on the wire:
#   "109,...,*KA=..." / "109,...,+AR40=..." -> the MODULE/HUB's OWN
#     identity broadcasting its status. NOT to be reused as our sender id
#     (device ignores/loops commands that claim to be from itself).
#   "099,155,*AR=001A040203" (and 099,158 / 099,159 / 099,160...) -> a
#     CLIENT session's real, working *AR= commands (mobile app's own
#     session sending real accepted commands). This is genuinely honored
#     by the device, so we mirror it for our own outgoing commands.
# Official PDF's bare "*AR=...\r" (no prefix) examples are the LOGICAL
# payload only - real wire traffic always carries this <id>,<seq>, prefix.
# ------------------------------------------------------------------ #
CLIENT_SENDER_ID = "099"
KEEPALIVE_INTERVAL = 5

# ------------------------------------------------------------------ #
# Periodic resync (soft-reconnect)
#
# Confirmed via real-world test: device apna CORRECT, up-to-date state
# sirf ek NAYE connection ke initial burst par deta hai (isi wajah se
# Raylogic App band-khol karne par sahi status dikhata hai, chahe HA se
# change kiya ho). Device kisi bhi channel (Relay ho ya Dimmer) ka state
# change doosre already-connected sessions ko live broadcast NAHI karta.
#
# Isliye HA yahan periodically apna connection khud band-khol karta hai
# (background mein, entities/commands mein koi rukawat nahi) - bilkul
# App reopen karne jaisa hi effect - taaki dono taraf (App se kiya gaya
# change HA mein, aur HA se kiya gaya change App mein) kuch hi second mein
# sync ho jaaye, bina live-push ke bharose rahe.
# ------------------------------------------------------------------ #
RESYNC_INTERVAL = 45
