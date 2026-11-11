#!/usr/bin/env python3
"""Make a Home Assistant dashboard that shows every panel where it sits on
the roof, with live power and DC voltage.

Usage: ha-dashboard.py <pm.conf> [--entity-id PATTERN] > dashboard.yaml

pm.conf is /var/sb/pm.conf from the box (the Power Manager stores each
panel's position from commissioning). Home Assistant builds the entity IDs from
the device and sensor names the bridge announces; --entity-id and
--total-id take a pattern with {serial}, {last4} and {slug} if yours
differ.
Paste the output into a new dashboard: Settings > Dashboards > Add
dashboard > New dashboard from scratch, then Edit > Raw configuration
editor. Only built-in cards are used.
"""
import argparse
import base64
import json
import sys

SCALE = 0.7897          # the vendor layout tool's panel scale
PAD = 30
MAX_W = 225             # Pantheon maximum AC output
# Bridge sensor key -> the slug Home Assistant makes from its name.
SLUG = {'power': 'power', 'energy': 'energy', 'dc_volts': 'dc_voltage',
        'ac_volts': 'ac_voltage', 'frequency': 'grid_frequency'}


def panels(conf):
    mi = json.load(open(conf))['summary'][0]['microinverters']
    out = []
    for serial, v in mi.items():
        w, h = v['width'] * SCALE, v['height'] * SCALE
        if v.get('rotation', 0) % 180 == 90:
            w, h = h, w
        out.append({'serial': serial, 'x': v['x'], 'y': v['y'], 'w': w, 'h': h})
    return out


def svg(ps, x0, y0, width, height):
    cells = []
    for p in ps:
        x, y, w, h = p['x'] - x0, p['y'] - y0, p['w'], p['h']
        cells.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" '
            f'fill="url(#cell)" stroke="#8aa4c8" stroke-width="1.5"/>')
        # cell grid: 6 x 12 cells on the long side, like a 72-cell panel
        cols, rows = (12, 6) if w > h else (6, 12)
        for i in range(1, cols):
            cells.append(f'<line x1="{x + w * i / cols:.1f}" y1="{y:.1f}" x2="{x + w * i / cols:.1f}" '
                         f'y2="{y + h:.1f}" stroke="#2c4a75" stroke-width="0.6"/>')
        for j in range(1, rows):
            cells.append(f'<line x1="{x:.1f}" y1="{y + h * j / rows:.1f}" x2="{x + w:.1f}" '
                         f'y2="{y + h * j / rows:.1f}" stroke="#2c4a75" stroke-width="0.6"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}">'
            '<defs><linearGradient id="cell" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#1d3557"/><stop offset="1" stop-color="#0d1b2a"/>'
            '</linearGradient></defs>'
            f'<rect width="{width:.0f}" height="{height:.0f}" rx="12" fill="#3a3f44"/>'
            + ''.join(cells) + '</svg>')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pm_conf')
    ap.add_argument('--entity-id', default='sensor.sunpower_panel_{last4}_{slug}')
    ap.add_argument('--total-id', default='sensor.sunpower_power_manager_total_{slug}')
    ap.add_argument('--title', default='Solar')
    args = ap.parse_args()

    ps = panels(args.pm_conf)
    x0 = min(p['x'] for p in ps) - PAD
    y0 = min(p['y'] for p in ps) - PAD
    width = max(p['x'] + p['w'] for p in ps) + PAD - x0
    height = max(p['y'] + p['h'] for p in ps) + PAD - y0
    image = 'data:image/svg+xml;base64,' + base64.b64encode(
        svg(ps, x0, y0, width, height).encode()).decode()

    def eid(p, key):
        return args.entity_id.format(serial=p['serial'], last4=p['serial'][-4:], slug=SLUG[key])

    total = args.total_id.format(slug='power')
    elements = []
    for p in sorted(ps, key=lambda p: (p['y'], p['x'])):
        cx = (p['x'] - x0 + p['w'] / 2) / width * 100
        cy = (p['y'] - y0 + p['h'] / 2) / height * 100
        for key, dy, size, weight in (('power', -9, 'clamp(11px, 2.2vw, 20px)', 700),
                                      ('dc_volts', 9, 'clamp(9px, 1.4vw, 13px)', 400)):
            elements.append({
                'type': 'state-label', 'entity': eid(p, key),
                'tap_action': {'action': 'more-info'},
                'style': {'left': f'{cx:.2f}%', 'top': f'{cy:.2f}%',
                          'transform': f'translate(-50%, calc(-50% + {dy}px))',
                          'color': '#ffd166' if key == 'power' else '#c9d6e8',
                          'font-size': size, 'font-weight': weight,
                          'text-shadow': '0 1px 2px #000', 'white-space': 'nowrap',
                          'pointer-events': 'auto'}})

    first = sorted(ps, key=lambda p: p['serial'])[0]
    dashboard = {'title': args.title, 'views': [{
        'title': 'Roof', 'path': 'roof', 'icon': 'mdi:solar-panel-large',
        'cards': [
            {'type': 'picture-elements', 'image': image, 'elements': elements},
            {'type': 'horizontal-stack', 'cards': [
                {'type': 'gauge', 'entity': total, 'name': 'Now', 'min': 0,
                 'max': MAX_W * len(ps), 'needle': True,
                 'severity': {'green': MAX_W * len(ps) // 2, 'yellow': MAX_W * len(ps) // 5,
                              'red': 0}},
                {'type': 'entities', 'entities': [
                    {'entity': args.total_id.format(slug='energy'), 'name': 'Lifetime energy'},
                    {'entity': eid(first, 'ac_volts'), 'name': 'Grid voltage'},
                    {'entity': eid(first, 'frequency'), 'name': 'Grid frequency'}]}]},
            {'type': 'history-graph', 'title': 'Total power', 'hours_to_show': 48,
             'entities': [{'entity': total, 'name': 'Total'}]},
            {'type': 'statistics-graph', 'title': 'Power per panel (hourly mean)',
             'chart_type': 'line', 'period': 'hour', 'days_to_show': 3,
             'stat_types': ['mean'], 'hide_legend': True,
             'entities': [eid(p, 'power') for p in sorted(ps, key=lambda p: p['serial'])]},
        ]}]}
    json.dump(dashboard, sys.stdout, indent=2)  # JSON is valid YAML
    print()


if __name__ == '__main__':
    main()
