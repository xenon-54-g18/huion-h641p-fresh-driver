#!/usr/bin/env python3
"""huion-fresh-driver: express-key remapper for Huion H641P (kernel-native).

- The PEN is 100% native (kernel hid driver): BTN_TOOL_PEN/BTN_TOUCH/pressure,
  no vanish bug, no userspace driver needed.
- Express keys arrive as firmware-fixed combos on the dedicated
  "Tablet_H641P Keyboard" node: B / I / E / Ctrl+S / Space / Ctrl+Alt+Z.
- This daemon exclusively grabs that node (firmware letters never reach apps)
  and re-emits user chords through a virtual uinput keyboard.

combo -> chord (edit COMBOS to taste; ctrl/alt/shift modifiers detected):
"""

import os, sys, time
from evdev import InputDevice, UInput, ecodes

TARGET = "Tablet_H641P Keyboard"

K = ecodes
CTRL, SHIFT, ALT = K.KEY_LEFTCTRL, K.KEY_LEFTSHIFT, K.KEY_LEFTALT

# brand new physical order (verified live):
#  1=B 2=I 3=E 4=Ctrl+S 5=Space 6=Ctrl+Alt+Z
COMBOS = {
    frozenset([K.KEY_B]):                     [(CTRL, 1), (K.KEY_Z, 1), (K.KEY_Z, 0), (CTRL, 0)],      # b1 undo
    frozenset([K.KEY_I]):                     [(CTRL, 1), (SHIFT, 1), (K.KEY_P, 1), (K.KEY_P, 0),
                                               (SHIFT, 0), (CTRL, 0)],                                 # b2 pen
    frozenset([K.KEY_E]):                     [(CTRL, 1), (SHIFT, 1), (K.KEY_E, 1), (K.KEY_E, 0),
                                               (SHIFT, 0), (CTRL, 0)],                                 # b3 eraser
    frozenset([CTRL, K.KEY_S]):               [(CTRL, 1), (SHIFT, 1), (K.KEY_H, 1), (K.KEY_H, 0),
                                               (SHIFT, 0), (CTRL, 0)],                                 # b4 highlight
    frozenset([K.KEY_SPACE]):                 [(CTRL, 1), (K.KEY_D, 1), (K.KEY_D, 0), (CTRL, 0)],      # b5 add page
    frozenset([CTRL, ALT, K.KEY_Z]):          [(K.KEY_F9, 1), (K.KEY_F9, 0)],                         # b6 menu
}

names = {
    frozenset([K.KEY_B]): "b1 undo",
    frozenset([K.KEY_I]): "b2 pen",
    frozenset([K.KEY_E]): "b3 eraser",
    frozenset([CTRL, K.KEY_S]): "b4 highlight",
    frozenset([K.KEY_SPACE]): "b5 add page",
    frozenset([CTRL, ALT, K.KEY_Z]): "b6 menu",
}
NEEDED = set()
for chord in COMBOS.values():
    for code, _ in chord:
        NEEDED.add(code)
NEEDED |= {CTRL, SHIFT, ALT}


def find_node():
    import glob
    for path in sorted(glob.glob('/sys/class/input/event*/device/name')):
        try:
            with open(path) as f:
                if TARGET in f.read():
                    return '/dev/input/' + os.path.basename(os.path.dirname(os.path.dirname(path)))
        except OSError:
            pass
    return None


def main():
    ui = UInput(name='huion-fresh-keyboard', bustype=K.BUS_USB,
                vendor=0x256c, product=0x6677, version=1,
                events={K.EV_KEY: sorted(NEEDED)})
    print("virtual keyboard ready", flush=True)

    def send(code, val):
        ui.write(K.EV_KEY, code, val)
        ui.syn()

    down = set()          # currently held tablet keys

    def serve(dev):
        for ev in dev.read_loop():
            if ev.type != K.EV_KEY:
                continue
            if ev.value == 1:
                down.add(ev.code)
                combo = frozenset(down)
                if combo in COMBOS:
                    chord = COMBOS[combo]
                    for code, val in chord:
                        send(code, val)
                    print(f"[{time.strftime('%H:%M:%S')}] fired {names.get(combo, '?')}", flush=True)
                    down.clear()  # ups will be ignored; fresh set for next press
            elif ev.value == 0:
                down.discard(ev.code)
            # anything else (repeats) ignored

    # hotplug-resilient outer loop:
    # unplug/re-enumerate/mode-switch -> wait for the node to come back
    attempt = 0
    while attempt < 5 or attempt == 5:
        node = find_node()
        if node is None:
            attempt += 1
            if attempt == 1:
                print("tablet keyboard node not found; waiting (hotplug)...", flush=True)
            time.sleep(2)
            continue
        attempt = 0
        print(f"tablet keyboard: {node}", flush=True)
        try:
            dev = InputDevice(node)
            try:
                dev.grab()
                print("EVIOCGRAB ON: firmware letters suppressed", flush=True)
            except Exception as e:
                print(f"WARN: grab failed ({e}) — letters will leak to apps", flush=True)
            serve(dev)
            print("read_loop ended; re-scanning node...", flush=True)
        except Exception as e:
            print(f"device error ({e.__class__.__name__}: {e}); hotplug retry...", flush=True)
        time.sleep(2)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
