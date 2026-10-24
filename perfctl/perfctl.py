#!/usr/bin/env python3
"""perfctl - tray icon and CLI for CPU cooler fan/pump boost and CPU freq boost.

Passive by design: setting the fans uploads a curve to the cooler hardware,
which then runs it on its own. Nothing here runs a control loop, so if this
program dies the fans keep following the last curve. Nothing is persisted.
"""

import argparse
import contextlib
import glob
import os
import sys

CPU_BOOST_PATH = '/sys/devices/system/cpu/cpufreq/boost'

# Normal fan curve: (liquid temp °C, duty %), temperatures strictly
# increasing, interpolated in hardware. At most 6 points; liquidctl pads
# with (60 °C, 100 %) as a failsafe.
NORMAL_CURVE = [(20, 25), (30, 30), (33, 40), (36, 55), (39, 75), (42, 100)]

# Pump speed modes supported by the cooler hardware, slowest first.
PUMP_MODES = ['quiet', 'balanced', 'performance']

ICON_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'icons')
POLL_SECONDS = 3


# --- API ---------------------------------------------------------------------

def get_cpu_boost():
    with open(CPU_BOOST_PATH) as f:
        return f.read().strip() == '1'


def set_cpu_boost(enabled):
    with open(CPU_BOOST_PATH, 'w') as f:
        f.write('1' if enabled else '0')


def cpu_boost_writable():
    return os.access(CPU_BOOST_PATH, os.W_OK)


def get_cpu_temp():
    """Tctl in °C from k10temp, or None."""
    for hwmon in glob.glob('/sys/class/hwmon/hwmon*'):
        try:
            with open(os.path.join(hwmon, 'name')) as f:
                if f.read().strip() != 'k10temp':
                    continue
            with open(os.path.join(hwmon, 'temp1_input')) as f:
                return int(f.read()) / 1000
        except OSError:
            pass
    return None


def boosted_curve(floor):
    """The normal curve, with every duty raised to at least floor %."""
    floor = max(0, min(100, int(floor)))
    return [(temp, max(duty, floor)) for temp, duty in NORMAL_CURVE]


def _find_cooler():
    from liquidctl import find_liquidctl_devices
    for dev in find_liquidctl_devices():
        if hasattr(dev, 'set_speed_profile') and 'Hydro' in dev.description:
            return dev
    raise RuntimeError('no supported cooler found')


@contextlib.contextmanager
def _cooler():
    """Connected cooler. On Linux, liquidctl's PyUSB backend never frees the
    USB handle on disconnect, leaking one fd per connection; free it here."""
    dev = _find_cooler()
    try:
        with dev.connect():
            yield dev
    finally:
        usbdev = getattr(dev.device, 'usbdev', None)
        if usbdev is not None:
            import usb.util
            usb.util.dispose_resources(usbdev)


def get_cooler_status():
    """Dict of cooler status, e.g. {'Liquid temperature': 32.6, ...}."""
    with _cooler() as dev:
        return {key: value for key, value, _unit in dev.get_status()}


def set_fan_boost(floor):
    """Upload the normal curve raised to floor % (0 = normal curve)."""
    with _cooler() as dev:
        # initialize() also sets pump mode; keep the current one.
        status = {key: value for key, value, _unit in dev.get_status()}
        dev.initialize(pump_mode=status.get('Pump mode', 'balanced'))
        dev.set_speed_profile('fan', boosted_curve(floor))


def set_pump_mode(mode):
    """Set the pump speed mode, one of PUMP_MODES. Leaves the fan curve as is."""
    if mode not in PUMP_MODES:
        raise ValueError(f'unknown pump mode {mode!r}')
    with _cooler() as dev:
        dev.initialize(pump_mode=mode)


# --- Tray --------------------------------------------------------------------

def run_tray():
    import gi
    gi.require_version('Gdk', '3.0')
    gi.require_version('Gtk', '3.0')
    gi.require_version('XApp', '1.0')
    from gi.repository import Gdk, GLib, Gtk, XApp

    class Tray:
        def __init__(self):
            self.fan_floor = None  # unknown until set by us
            self.pending_floor = None
            self.pump_mode = None
            self.updating = False  # set while refresh() syncs widgets

            self.icon = XApp.StatusIcon()
            self.icon.set_name('perfctl')
            self.icon.connect('activate', self.on_activate)

            menu = Gtk.Menu()
            quit_item = Gtk.MenuItem(label='Quit')
            quit_item.connect('activate', lambda *_: Gtk.main_quit())
            menu.append(quit_item)
            menu.show_all()
            self.icon.set_secondary_menu(menu)

            self.build_popup()
            self.refresh()
            GLib.timeout_add_seconds(POLL_SECONDS, self.refresh)

        def build_popup(self):
            win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
            win.set_decorated(False)
            win.set_skip_taskbar_hint(True)
            win.set_skip_pager_hint(True)
            win.set_keep_above(True)
            win.set_type_hint(Gdk.WindowTypeHint.DIALOG)
            win.set_position(Gtk.WindowPosition.MOUSE)
            win.connect('focus-out-event', lambda *_: win.hide())
            win.connect('delete-event', lambda *_: win.hide() or True)

            grid = Gtk.Grid(row_spacing=8, column_spacing=12, margin=12)
            win.add(grid)

            grid.attach(Gtk.Label(label='Fan boost', xalign=0), 0, 0, 1, 1)
            self.fan_label = Gtk.Label(xalign=1)
            grid.attach(self.fan_label, 1, 0, 1, 1)

            self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
            self.scale.set_draw_value(False)
            self.scale.set_size_request(220, -1)
            for mark in (0, 25, 50, 75, 100):
                self.scale.add_mark(mark, Gtk.PositionType.BOTTOM, None)
            self.scale.connect('value-changed', self.on_scale_changed)
            grid.attach(self.scale, 0, 1, 2, 1)

            grid.attach(Gtk.Label(label='Pump', xalign=0), 0, 2, 2, 1)
            pump_box = Gtk.Box(homogeneous=True)
            pump_box.get_style_context().add_class('linked')
            self.pump_buttons = {}
            group = None
            for mode in PUMP_MODES:
                button = Gtk.RadioButton(label=mode, group=group, draw_indicator=False)
                group = group or button
                button.connect('toggled', self.on_pump_toggled, mode)
                pump_box.add(button)
                self.pump_buttons[mode] = button
            grid.attach(pump_box, 0, 3, 2, 1)

            grid.attach(Gtk.Label(label='CPU frequency boost', xalign=0), 0, 4, 1, 1)
            self.boost_switch = Gtk.Switch(halign=Gtk.Align.END)
            self.boost_handler = self.boost_switch.connect('notify::active', self.on_boost_toggled)
            grid.attach(self.boost_switch, 1, 4, 1, 1)

            self.status_label = Gtk.Label(xalign=0)
            self.status_label.get_style_context().add_class('dim-label')
            grid.attach(self.status_label, 0, 5, 2, 1)

            grid.show_all()
            self.popup = win

        def on_activate(self, _icon, button, _time):
            if button != 1:
                return
            if self.popup.get_visible():
                self.popup.hide()
            else:
                self.refresh()
                self.popup.present()

        def on_scale_changed(self, scale):
            # Debounce: write to the cooler once the slider settles.
            if self.pending_floor is None:
                GLib.timeout_add(400, self.apply_fan)
            self.pending_floor = int(scale.get_value())
            self.update_fan_label(self.pending_floor)

        def apply_fan(self):
            floor, self.pending_floor = self.pending_floor, None
            try:
                set_fan_boost(floor)
                self.fan_floor = floor
            except Exception as e:
                self.error(f'Fan: {e}')
            self.refresh()
            return False

        def on_pump_toggled(self, button, mode):
            if self.updating or not button.get_active():
                return
            try:
                set_pump_mode(mode)
            except Exception as e:
                self.error(f'Pump: {e}')
            self.refresh()

        def on_boost_toggled(self, switch, _param):
            try:
                set_cpu_boost(switch.get_active())
            except OSError as e:
                self.error(f'CPU boost: {e}')
            self.refresh()

        def update_fan_label(self, floor):
            if floor is None:
                self.fan_label.set_text('not set')
            elif floor == 0:
                self.fan_label.set_text('normal')
            else:
                self.fan_label.set_text(f'min {floor} %')

        def error(self, text):
            dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                                       buttons=Gtk.ButtonsType.CLOSE, text=text)
            dialog.run()
            dialog.destroy()

        def refresh(self):
            lines = []
            try:
                status = get_cooler_status()
                fans = [v for k, v in status.items() if k.startswith('Fan')]
                self.pump_mode = status['Pump mode']
                lines.append(f"Liquid {status['Liquid temperature']:.1f} °C, "
                             f"fans {', '.join(str(int(f)) for f in fans)} rpm")
                lines.append(f"Pump {status['Pump speed']} rpm ({self.pump_mode})")
                self.updating = True
                self.pump_buttons[self.pump_mode].set_active(True)
                self.updating = False
            except Exception as e:
                lines.append(f'Cooler: {e}')
            cpu_temp = get_cpu_temp()
            if cpu_temp is not None:
                lines.append(f'CPU {cpu_temp:.1f} °C')

            boost = get_cpu_boost()
            self.boost_switch.handler_block(self.boost_handler)
            self.boost_switch.set_active(boost)
            self.boost_switch.handler_unblock(self.boost_handler)
            self.boost_switch.set_sensitive(cpu_boost_writable())
            lines.append(f"CPU boost {'on' if boost else 'off'}")

            if self.pending_floor is None:
                self.update_fan_label(self.fan_floor)
            self.status_label.set_text('\n'.join(lines))

            boosted = bool(self.fan_floor) or self.pump_mode == 'performance'
            self.icon.set_icon_name(os.path.join(
                ICON_DIR, 'perfctl-boost.svg' if boosted else 'perfctl-normal.svg'))
            self.icon.set_tooltip_text('perfctl\n' + '\n'.join(lines))
            return True

    Tray()
    Gtk.main()


# --- CLI ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status', help='show cooler and CPU boost status')
    fan = sub.add_parser('fan', help='set fan boost: minimum duty %%, 0 = normal curve')
    fan.add_argument('floor', type=int)
    pump = sub.add_parser('pump', help='set pump speed mode')
    pump.add_argument('mode', choices=PUMP_MODES)
    boost = sub.add_parser('cpuboost', help='enable/disable CPU frequency boost')
    boost.add_argument('state', choices=['on', 'off'])
    sub.add_parser('tray', help='run the tray icon')
    args = parser.parse_args()

    if args.cmd == 'status':
        for key, value in get_cooler_status().items():
            print(f'{key}: {value}')
        print(f'CPU temperature: {get_cpu_temp()}')
        print(f"CPU boost: {'on' if get_cpu_boost() else 'off'}")
    elif args.cmd == 'fan':
        set_fan_boost(args.floor)
        print('Fan curve:', ' '.join(f'{t}°C:{d}%' for t, d in boosted_curve(args.floor)))
    elif args.cmd == 'pump':
        set_pump_mode(args.mode)
    elif args.cmd == 'cpuboost':
        set_cpu_boost(args.state == 'on')
    elif args.cmd == 'tray':
        run_tray()


if __name__ == '__main__':
    sys.exit(main())
