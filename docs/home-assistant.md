# Home Assistant over MQTT

`overlay/home/sunbridge/` is a small bridge that runs **on the box** and
publishes every microinverter to Home Assistant through an MQTT broker
(for example the Mosquitto add-on). It uses MQTT discovery, so the devices
and sensors appear on their own.

- Python 2.6, which the box already has; no extra packages, nothing
  installed on the internal flash
- Its own minimal MQTT 3.1.1 client (`mqtt.py`, about 120 lines: connect
  with user and password and a last will, publish, ping)
- Never writes to disk: state is kept in memory, no log files, `.pyc`
  files are disabled (`python -B`), and output goes to `/dev/null`
- Started at boot by `/home/sunpwrscripts/30-sunbridge.sh`, which
  restarts it if it exits

## Setup

1. In Home Assistant, install the Mosquitto broker add-on and the MQTT
   integration, and create a user for the bridge.
2. Copy `overlay/home/sunbridge/sunbridge.conf.example`, fill in the
   broker address and the user, and pass it to
   `tools/apply-overlay.py --mqtt-conf` ([revive.md](revive.md)).
   On a running box you can copy it to
   `/home/sunbridge/sunbridge.conf` instead.

| Setting | Default | |
|---|---|---|
| `host` | `homeassistant.local` | broker address |
| `port` | 1883 | |
| `user`, `password` | none | |
| `interval` | 300 | seconds between poll cycles |
| `sbti_timeout` | 60 | seconds before a hung `sbti` call is killed |
| `prefix` | `sunpower` | MQTT topic prefix |
| `discovery_prefix` | `homeassistant` | |

## What you get

One device per microinverter ("SunPower panel 1234", the last four digits
of its serial), linked to a "SunPower Power Manager" device, with:

| Sensor | Unit | Class |
|---|---|---|
| Power | W | power, measurement |
| Energy (lifetime) | kWh | energy, total_increasing |
| DC power, DC voltage, DC current | W, V, A | |
| AC voltage, AC current, grid frequency | V, A, Hz | |
| Temperature | °C | |
| Status | text | |
| Reachable | on/off | connectivity |

Plus "Total power" and "Total energy" on the Power Manager device. Use the
energy sensors in Home Assistant's Energy dashboard as solar production.

## Topics

| Topic | Retained | Payload |
|---|---|---|
| `sunpower/bridge/status` | yes | `online` / `offline` (also the last will) |
| `sunpower/<serial>/state` | yes | JSON: `reachable`, `power`, `dc_watts`, `dc_amps`, `ac_amps`, and when known `dc_volts`, `ac_volts`, `frequency`, `temperature`, `status` |
| `sunpower/<serial>/energy` | yes | `{"energy": <kWh>}` |
| `sunpower/total/power`, `sunpower/total/energy` | yes | |
| `homeassistant/sensor/sunpower_<serial>/<key>/config` | yes | discovery |

## Failure handling

| Situation | What the bridge does |
|---|---|
| Broker or network down (also at boot) | keeps polling, retries the broker every cycle, never exits |
| Connection dies silently | a PING round trip every cycle detects it and reconnects |
| Home Assistant restarts | discovery and states are retained, so they come back at once |
| Bridge stops | publishes `offline`; on a crash the broker sends the last will, so all sensors become unavailable |
| `sbti` hangs | killed after `sbti_timeout` |
| Night, or an inverter does not answer | power and currents 0, voltages/frequency/temperature unknown, `reachable` off; energy keeps its last value |
| All inverters silent | only one inverter (rotating) is asked per cycle, instead of spending ~30 s of powerline time on each |
| Lifetime energy decreases or jumps (the 2013 "lifetime energy spike" bug) | the value is rejected; the total is only published when every inverter is known |

Tested on the box against a test broker: broker down at start, broker
coming up, broker restart, SIGTERM, `kill -9`, and night.

## Status

**The parser for `sbti -m` output is not finished**: it needs a capture of
real output in daylight. Until then the bridge reports every inverter as
unreachable. See [inverters.md](inverters.md).

## Run it by hand

Stop the boot-time copy first; two bridges with the same MQTT client ID
keep disconnecting each other.

```sh
ssh sunpower
pkill -f 30-sunbridge.sh; pkill -f sunbridge.py
cd /home/sunbridge
python -B sunbridge.py -v --once      # one cycle, messages on stderr
```

Reboot (or run `bash /home/sunpwrscripts/30-sunbridge.sh &`) to start it
again.
