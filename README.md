# Huion H641P "fresh driver" — kernel-native pen + express-key remapper

Linux driver replacement stack for the **Huion H641P** (USB ID `256c:0066`)
on **Ubuntu 26.04 / GNOME (Wayland)**. Fixes the recurring "pen vanishes
after 1–2 s of rest / while writing" bug and gives the six express keys
custom, useful actions — with **no proprietary driver and no
OpenTabletDriver** running.

## TL;DR

| Piece | What runs | Why |
|---|---|---|
| Pen | **Nothing** — the kernel's own HID driver (`hid_generic`/`usbhid`) serves a complete digitizer: `BTN_TOOL_PEN` proximity, `BTN_TOUCH` tip, pressure, correct 160×100 mm area on `event*` "HUION Huion Tablet_H641P Pen" | The vanishing bug comes only from Huion's userspace layer; vanilla kernel support has no defect |
| Express keys | `huion-fresh-driver.py` (3rd-party dep: `python3-evdev`) — grabs the "Tablet_H641P Keyboard" node, suppresses the firmware's useless outputs, re-emits configurable chords via a virtual `uinput` keyboard | Firmware hard-wires buttons to fixed combos (B / I / E / Ctrl+S / Space / Ctrl+Alt+Z) that apps ignore |

## The cause of the pen-vanish bug (root cause, proven)

Every capture of the proprietary Huion driver (`huionCore -d`, v15.0.0.187)
showed the same signature:

1. `huionCore` **claims the USB interface via usbfs**, which starves the
   kernel HID driver — the real pen node (`HUION Huion Tablet_H641P Pen`)
   receives **zero events** while drawing (checked via `libevdev` capture +
   `EVIOCGKEY` snapshots + hidraw reads).
2. All traffic is relayed to a **virtual "fake" pen** created with `uinput`
   (`HUION 256C PEN STYLUS`, absurd 7×4 mm geometry) whose event stream
   contains `ABS_X/ABS_Y/PRESSURE` only — **never** `BTN_TOOL_PEN`, never
   `BTN_TOUCH`. Verified with multiple simultaneous evdev captures and
   raw hidraw reads over several minutes of active use.
3. Without tool-key events, consumers (libinput → mutter → Xournal++, GTK)
   never get a sustained "in prox / tip down" state. The result is exactly
   the reported symptom: the cursor dot disappears after 1–2 s of rest,
   during writing, in every app, and returns only after the pen moves.
4. The virtual devices are also created with broken setup data:
   duplicate pen instances, bogus resolutions, malformed `uhid` writes
   (kernel logs `Wrong size written to uhid: 4368 != 8`, `-EFAULT`), and a
   world-writable `/usr/lib/udev/rules.d/20-huion.rules` (security issue).

The bug reappears **whenever the driver is (re)installed or launched** —
it is inherent to the driver's architecture, not a configuration problem.

OpenTabletDriver (v0.6.7) was tried as a replacement: it drives the tablet
correctly at the kernel level (tip state held through multi-second holds),
but the same "cursor dot disappears at rest" persisted at the
libinput/compositor level, and it still ran a userspace daemon — so it was
dropped in favour of 100 % native support once the express keys were
solved (the only thing native mode never provided).

## The express-key mechanics (why the remapper is needed)

The keyboard interface's HID descriptor declares:
* report **0x03** — standard keyboard array (modifier byte + 6 keys)
* report **0x04** — consumer-control array (media/zoom usages)

The six physical buttons are **firmware-premapped** to fixed combos:

| Physical button (top→bottom) | Firmware emits | Default action after remap |
|---|---|---|
| 1 | plain `B` | `Ctrl+Z` — undo |
| 2 | plain `I` | `Ctrl+Shift+P` — pen tool |
| 3 | plain `E` | `Ctrl+Shift+E` — eraser |
| 4 | `Ctrl+S` | `Ctrl+Shift+H` — highlighter |
| 5 | `Space` | `Ctrl+D` — add page |
| 6 | `Ctrl+Alt+Z` | `F9` — menu |

The combos are useful for mapping verification (`--learn` mode prints every
raw evdev key), but useless as *user actions* — they type letters or fire
silent combos like Ctrl+S. The daemon distinguishes buttons by the set of
keycodes held simultaneously (see `COMBOS` dict in the script) and emits
the chosen chords through its own virtual keyboard,
so the firmware letters never reach your documents.

> Note: button 5 shares `Space`. Scroll/pan behaviour of the pad or a
> possible wheel is special (Space taps). If pan/scroll matters, remove or
> change the `frozenset([K.KEY_SPACE])` entry in `COMBOS`.

## Install

```bash
sudo apt install python3-evdev            # only non-kernel dependency
mkdir -p ~/.local/bin
cp huion-fresh-driver.py ~/.local/bin/
mkdir -p ~/.config/systemd/user
cp huion-fresh-driver.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now huion-fresh-driver.service
```

Also mask the broken driver's autostart if ever reinstalled:
`~/.config/autostart/huiontablet.desktop` with `[Desktop Entry] … Hidden=true`.
The pen needs **no** configuration.

## Update policy — why this can't rot like before

* **Pen driver updates come from the kernel itself** (`linux-image`
  packages) — always installed/updated via `apt`, no Huion involvement.
  Regressions in `hid-generic`/`usbhid` for this tablet are an upstream bug
  class that affects everyone and gets fixed upstream, unlike the
  proprietary V15 driver's permanent defects.
* The only userspace piece (`huion-fresh-driver.py`) depends solely on the
  stable `/dev/input/evdev` + `uinput` ABIs — unchanged for years, no
  dependency on Huion, no dependency on OpenTabletDriver.
* A minimal udev rule grants uaccess on `/dev/uinput`
  (`/etc/udev/rules.d/50-uinput-uaccess.rules`, installed by
  `install.sh`-equivalent steps) so the remapper never relies on any other
  package's rules.
* Remove nothing else; if the Huion package is ever installed (e.g. by a
  software-centre suggestion) it will grab the USB again — just run
  `sudo apt purge huiontablet && sudo rm /usr/lib/udev/rules.d/20-huion.rules`.

## Daily-runtime / troubleshooting checklist (use this, not a search engine)

```bash
# 1. is the daemon alive and grabbing?
systemctl --user status huion-fresh-driver

# 2. is a proprietary driver running? (this is always BAD on this setup)
pgrep -af 'huionCore|huiontablet manual_launch'
# → kill the PIDs, pen comes back instantly (native path re-claims)

# 3. is pen device healthy (160x100 mm, ID_INPUT_TABLET=1)?
cat /sys/class/input/event*/device/name | grep -i huion

# 4. verify kernel pen stream has BTN_TOOL_PEN/BTN_TOUCH transitions:
sudo libinput debug-events | grep -E 'PROXIMITY|TIP|AXIS'   # or capture /dev/input/eventN with evdev
```

If Xournal++/apps ever lose the pen cursor after a driver auto-update
installs the Huion daemon again: **purge it, kill daemons, done.** The
kernel path rebinds instantly, no reboot needed.

## Files (this install)

| Path | Role |
|---|---|
| `~/.local/bin/huion-fresh-driver.py` | the running remapper daemon |
| `~/.config/systemd/user/huion-fresh-driver.service` | autostart + restart-on-failure |
| `/etc/udev/rules.d/50-uinput-uaccess.rules` | grants the user `/dev/uinput` (uaccess) |
| this `README.md`, `install.sh` | reproducible project |

## Repo coverage

OpenTabletDriver and its `.NET` runtime were also removed from this
machine (the same detour is unnecessary for new users: the kernel + this
remapper is the whole stack).

## Reproducibility

`install.sh` performs the steps from **Install** idempotently. To relocate,
edit `ExecStart` in the service file. To stop for good:
`systemctl --user disable --now huion-fresh-driver.service`.

## Licences / credits

Debug tooling used during the root-cause hunt: `libinput debug-events`,
`evdev` (python), `EVIOCGKEY`, raw hidread captures, udevadm, and reading
`evdev-tablet.c` from the libinput 1.31.1 sources to narrow the
proximity-transition mechanism. No proprietary code was copied.
