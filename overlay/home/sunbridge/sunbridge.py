"""Publish SolarBridge microinverter data to Home Assistant over MQTT.

Polls each inverter with the vendor tool `sbti -m <serial>` and publishes
retained JSON states plus Home Assistant discovery configs. Runs forever and
never writes to disk itself: all state is in memory, nothing is logged unless -v is
given (then to stderr).

    python -B sunbridge.py [-c sunbridge.conf] [-v] [--once]
"""
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time

import mqtt

HERE = os.path.dirname(os.path.abspath(__file__))
SBTI = '/home/data_logger/bin/sbti'
PM_CONF = '/var/sb/pm.conf'
VERBOSE = False

DEFAULTS = {
    'host': 'homeassistant.local', 'port': 1883, 'user': '', 'password': '',
    'interval': 300,        # seconds between poll cycles
    'sbti_timeout': 60,     # seconds before a hung sbti call is killed
    'prefix': 'sunpower',
    'discovery_prefix': 'homeassistant',
    'ignore': [],           # serials of dead inverters: not polled, not in totals
}

# (key, name, unit, device_class, state_class) for each inverter sensor.
SENSORS = [
    ('power', 'Power', 'W', 'power', 'measurement'),
    ('energy', 'Energy', 'kWh', 'energy', 'total_increasing'),
    ('dc_watts', 'DC power', 'W', 'power', 'measurement'),
    ('dc_volts', 'DC voltage', 'V', 'voltage', 'measurement'),
    ('dc_amps', 'DC current', 'A', 'current', 'measurement'),
    ('ac_volts', 'AC voltage', 'V', 'voltage', 'measurement'),
    ('ac_amps', 'AC current', 'A', 'current', 'measurement'),
    ('frequency', 'Grid frequency', 'Hz', 'frequency', 'measurement'),
    ('temperature', 'Temperature', u'\u00b0C', 'temperature', 'measurement'),
    ('status', 'Status', None, None, None),
]

# Polls an inverter may miss before it counts as unreachable (0 W).
MISSED_POLLS = 5

# Largest believable energy increase per poll: 225 W max output, with margin.
MAX_KWH_PER_HOUR = 0.5


def log(msg):
    if VERBOSE:
        sys.stderr.write(time.strftime('%H:%M:%S ') + msg + '\n')


def load_config(path):
    cfg = dict(DEFAULTS)
    try:
        f = open(path)
        try:
            cfg.update(json.load(f))
        finally:
            f.close()
    except (IOError, ValueError), e:
        log('config %s: %s; using defaults' % (path, e))
    return cfg


def serials():
    """Inverter serials from the Power Manager config (no powerline traffic)."""
    try:
        f = open(PM_CONF)
        try:
            conf = json.load(f)
        finally:
            f.close()
        return sorted(conf['summary'][0]['microinverters'].keys())
    except (IOError, ValueError, KeyError, IndexError), e:
        log('pm.conf: %s' % e)
        return []


def run(args, timeout):
    """Run a command with a hard time limit; return (exit code, output)."""
    env = dict(os.environ, LD_LIBRARY_PATH='/home/data_logger/lib')
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=env, close_fds=True)
    except OSError, e:
        return -1, str(e)
    deadline = time.time() + timeout
    while p.poll() is None:
        if time.time() > deadline:
            try:
                p.kill()
            except OSError:
                pass
            p.wait()
            remove_stale_cache(2 * timeout)
            return -1, 'timeout'
        time.sleep(0.2)
    return p.returncode, p.stdout.read()


def remove_stale_cache(min_age):
    """A killed sbti leaves its half-written cache /var/sb/.sbidirect.mil-XXXXXX
    behind (libsbidirect prunes only its numbered copies). Remove those that
    are old enough not to belong to a running call."""
    now = time.time()
    try:
        names = os.listdir('/var/sb')
    except OSError:
        return
    for name in names:
        if name.startswith('.sbidirect.mil-'):
            path = os.path.join('/var/sb', name)
            try:
                if now - os.path.getmtime(path) > min_age:
                    os.unlink(path)
            except OSError:
                pass


def number(text):
    m = re.search(r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', text)
    return m and float(m.group(0))


# The labels `sbti -m` prints ("<label> = <value>", from the sbti binary),
# mapped to (sensor key, scale). Lifetime energy comes in Wh, printed like
# 4.24896e+06.
LABELS = {
    'Total Lifetime Energy in Watt hours': ('energy', 1e-3),
    'Present AC Power Generating in Watts': ('power', 1),
    'Average DC voltage over report period in Volts': ('dc_volts', 1),
    'DC Current in Amps': ('dc_amps', 1),
    'DC Power in Watts': ('dc_watts', 1),
    'AC Voltage line 1 to line 2': ('ac_volts', 1),
    'Measured Line AC Amperage in Amps': ('ac_amps', 1),
    'Line Frequency in Hertz': ('frequency', 1),
    'Temperature in celsius': ('temperature', 1),
}


def parse(output):
    """Turn `sbti -m` output into a sensor dict. Alert lines become the
    status; without any it is "ok"."""
    values, alerts = {}, []
    for line in output.splitlines():
        label, sep, value = line.partition('=')
        label = label.strip()
        if sep and label in LABELS:
            key, scale = LABELS[label]
            n = number(value)
            if n is not None:
                values[key] = round(n * scale, 3)
        elif line.strip().startswith('Alert '):
            alerts.append(line.strip())
    if 'power' in values:
        values['status'] = alerts and '; '.join(alerts)[:250] or 'ok'
    return values


class Bridge(object):
    def __init__(self, cfg):
        self.cfg = cfg
        p = cfg['prefix']
        self.status_topic = p + '/bridge/status'
        self.client = mqtt.Client(cfg['host'], int(cfg['port']), client_id=p + '-bridge',
                                  user=cfg['user'] or None, password=cfg['password'] or None,
                                  keepalive=int(cfg['interval']) * 3)
        self.connected = False
        self.energy = {}        # serial -> last accepted lifetime kWh
        self.energy_time = {}
        self.asleep = True      # no inverter answered in the last cycle (start by probing)
        self.last = {}          # serial -> (time, state) of its last answer
        self.probe = 0

    # -- MQTT ------------------------------------------------------------
    def ensure_connected(self, inverters):
        if self.connected:
            try:
                self.client.ping()
                return True
            except (socket.error, mqtt.MQTTError), e:
                log('broker connection lost: %s' % e)
                self.connected = False
        try:
            self.client.connect(self.status_topic, 'offline')
            self.client.publish(self.status_topic, 'online', retain=True)
            self.publish_discovery(inverters)
            self.connected = True
            log('connected to %s:%s' % (self.cfg['host'], self.cfg['port']))
        except (socket.error, mqtt.MQTTError), e:
            log('broker %s:%s unavailable: %s' % (self.cfg['host'], self.cfg['port'], e))
            self.client.close()
        return self.connected

    def publish(self, topic, payload):
        self.client.publish(topic, json.dumps(payload), retain=True)

    def publish_discovery(self, inverters):
        p, d = self.cfg['prefix'], self.cfg['discovery_prefix']
        hub = {'identifiers': [p + '_power_manager'], 'name': 'SunPower Power Manager',
               'manufacturer': 'SolarBridge', 'model': 'PV Supervisor'}
        for serial in inverters:
            device = {'identifiers': [p + '_' + serial], 'name': 'SunPower panel ' + serial[-4:],
                      'manufacturer': 'SolarBridge', 'model': 'Pantheon (ACPV Gen 1)',
                      'serial_number': serial, 'via_device': p + '_power_manager'}
            for key, name, unit, dclass, sclass in SENSORS:
                topic = p + '/' + serial + ('/energy' if key == 'energy' else '/state')
                cfg = {'name': name, 'unique_id': '%s_%s_%s' % (p, serial, key),
                       'object_id': '%s_%s_%s' % (p, serial[-4:], key),
                       'state_topic': topic, 'device': device,
                       'availability_topic': self.status_topic,
                       # Missing keys render as None, which HA shows as unknown.
                       'value_template': "{{ value_json.get('%s') }}" % key}
                for k, v in (('unit_of_measurement', unit), ('device_class', dclass),
                             ('state_class', sclass)):
                    if v:
                        cfg[k] = v
                self.publish('%s/sensor/%s_%s/%s/config' % (d, p, serial, key), cfg)
            self.publish('%s/binary_sensor/%s_%s/reachable/config' % (d, p, serial), {
                'name': 'Reachable', 'unique_id': '%s_%s_reachable' % (p, serial),
                'state_topic': p + '/' + serial + '/state', 'device': device,
                'availability_topic': self.status_topic, 'device_class': 'connectivity',
                'value_template': "{{ 'ON' if value_json.reachable else 'OFF' }}"})
        for key, name, unit, dclass, sclass in SENSORS[:2]:
            self.publish('%s/sensor/%s_total/%s/config' % (d, p, key), {
                'name': 'Total ' + name.lower(), 'unique_id': '%s_total_%s' % (p, key),
                'object_id': '%s_total_%s' % (p, key),
                'state_topic': '%s/total/%s' % (p, key), 'device': hub,
                'availability_topic': self.status_topic,
                'value_template': '{{ value_json.%s }}' % key,
                'unit_of_measurement': unit, 'device_class': dclass, 'state_class': sclass})

    # -- Polling ---------------------------------------------------------
    def accept_energy(self, serial, kwh, now):
        """Reject the known lifetime-energy spikes and any decrease."""
        last, when = self.energy.get(serial), self.energy_time.get(serial, now)
        if last is not None:
            hours = max((now - when) / 3600.0, int(self.cfg['interval']) / 3600.0)
            if kwh < last or kwh - last > MAX_KWH_PER_HOUR * hours:
                log('%s: rejected energy %.2f (last %.2f)' % (serial, kwh, last))
                return False
        self.energy[serial], self.energy_time[serial] = kwh, now
        return True

    def poll(self, serial):
        code, out = run([SBTI, '-m', serial], int(self.cfg['sbti_timeout']))
        values = code == 0 and parse(out) or {}
        return self.state(serial, values, code)

    def state(self, serial, values, code):
        """Inverter state; when it does not answer, output is zero and the
        voltages, frequency and temperature are unknown (left out). code is
        the sbti exit code, or None if the inverter was not asked."""
        state = {'reachable': bool(values)}
        for key in ('power', 'dc_watts', 'dc_amps', 'ac_amps'):
            state[key] = values.get(key, 0)
        for key in ('dc_volts', 'ac_volts', 'frequency', 'temperature'):
            if key in values:
                state[key] = values[key]
        state['status'] = values.get('status', 'unreachable')
        energy = values.get('energy')
        if energy is not None and not self.accept_energy(serial, energy, time.time()):
            energy = None
        if code is not None:
            log('%s: %s' % (serial, state['reachable'] and 'ok' or 'no answer (%d)' % code))
        return state, energy

    def cycle(self):
        inverters = serials()
        ignore = set(self.cfg['ignore'])
        active = [s for s in inverters if s not in ignore]
        results = [(s,) + self.state(s, {}, None) for s in inverters if s in ignore]
        if self.asleep and active:
            # Nothing answered last time (night): ask one inverter, rotating,
            # instead of spending ~30 s of powerline time on each of them.
            probe = active[self.probe % len(active)]
            self.probe += 1
            results += [(probe,) + self.poll(probe)]
            if results[-1][1]['reachable']:
                results += [(s,) + self.poll(s) for s in active if s != probe]
            else:
                results += [(s,) + self.state(s, {}, None) for s in active if s != probe]
        else:
            results += [(s,) + self.poll(s) for s in active]
        self.asleep = not [1 for _, state, _ in results if state['reachable']]
        # A missed answer is not 0 W: keep the last answer for a while, so a
        # powerline hiccup does not drop the panel and the total to zero.
        now, grace = time.time(), (MISSED_POLLS + 0.5) * int(self.cfg['interval'])
        fresh = []
        for serial, state, energy in results:
            if state['reachable']:
                self.last[serial] = (now, state)
            elif serial in self.last and now - self.last[serial][0] < grace:
                fresh.append((serial, None, None))  # keep the retained state
                continue
            fresh.append((serial, state, energy))
        results = fresh
        if not self.ensure_connected(inverters):
            return  # nothing is buffered; the next cycle sends fresh data
        p = self.cfg['prefix']
        try:
            for serial, state, energy in results:
                if state is None:
                    continue
                self.publish(p + '/' + serial + '/state', state)
                if energy is not None:
                    self.publish(p + '/' + serial + '/energy', {'energy': energy})
            total = 0
            for serial, state, _ in results:
                total += (state or self.last[serial][1])['power']
            self.publish(p + '/total/power', {'power': round(total, 1)})
            # Only when every inverter is known, or the total would drop.
            if active and len(self.energy) == len(active):
                self.publish(p + '/total/energy', {'energy': round(sum(self.energy.values()), 3)})
        except socket.error, e:
            log('publish failed: %s' % e)
            self.connected = False
            self.client.close()

    def stop(self, *_):
        if self.connected:
            try:
                self.client.publish(self.status_topic, 'offline', retain=True)
            except socket.error:
                pass
        self.client.disconnect()
        sys.exit(0)


def main():
    global VERBOSE
    args = sys.argv[1:]
    VERBOSE = '-v' in args
    conf = os.path.join(HERE, 'sunbridge.conf')
    if '-c' in args:
        conf = args[args.index('-c') + 1]
    cfg = load_config(conf)
    bridge = Bridge(cfg)
    signal.signal(signal.SIGTERM, bridge.stop)
    signal.signal(signal.SIGINT, bridge.stop)
    while True:
        start = time.time()
        try:
            bridge.cycle()
        except Exception, e:  # never die on bad data; the loop must keep going
            log('cycle failed: %r' % e)
        if '--once' in args:
            bridge.stop()
        time.sleep(max(5, int(cfg['interval']) - (time.time() - start)))


if __name__ == '__main__':
    main()
