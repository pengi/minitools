# perfctl

Tray icon (Cinnamon / XApp) and CLI for:

- **Fan boost**: raises the Corsair H150i Pro radiator fans. The slider is a
  minimum duty (0–100 %) applied on top of a normal fan curve, so it can
  never take the fans below normal. 0 = normal curve.
- **Pump mode**: selects the cooler's pump speed mode, `quiet` (~1050 rpm),
  `balanced` (~2070 rpm) or `performance` (~2820 rpm). These three modes
  are all the hardware offers; there is no pump duty or curve.
- **CPU frequency boost**: toggles `/sys/devices/system/cpu/cpufreq/boost`.

The tool is passive: it uploads a fan curve (on liquid temperature) to the
cooler via [liquidctl](https://github.com/liquidctl/liquidctl), and the
cooler runs it in hardware. Nothing is controlled in a loop, so if perfctl
crashes or quits the fans keep following the last curve. Nothing is
persisted: after a power cycle the cooler and CPU boost are back to their
defaults. The normal curve is `NORMAL_CURVE` at the top of `perfctl.py`.

## Usage

Left-click the tray icon for the popup with the slider, the pump mode
selector, the CPU boost switch and status (liquid temp, fan and pump rpm,
CPU temp). Right-click to quit. The icon turns orange while fan boost or
pump mode `performance` is active.

```
perfctl status          # cooler status, CPU temp, CPU boost
perfctl fan 60          # fans at least 60 %
perfctl fan 0           # normal curve
perfctl pump performance  # pump mode: quiet, balanced or performance
perfctl cpuboost off    # disable CPU frequency boost
perfctl tray            # run the tray icon
```

## Install

Needs the apt packages `liquidctl`, `python3-xapp`, `gir1.2-xapp-1.0`
(all present on Linux Mint once liquidctl is installed).

```
./install.sh              # install, autostart and start
./install.sh --uninstall
```

Installs to `~/.local/share/perfctl`, links `~/.local/bin/perfctl`, adds an
autostart entry, and (with sudo) adds `/etc/tmpfiles.d/perfctl.conf`, which
makes the boost file writable by your group at every boot.
