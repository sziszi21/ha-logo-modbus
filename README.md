# Siemens LOGO! Modbus TCP for Home Assistant

Custom integration that connects a **Siemens LOGO! 8** (8.3 / 8.4) to Home Assistant over **Modbus TCP**, set up entirely from the UI — no YAML.

For every configured LOGO! you get:

- one **switch** per output: `Q1 … Qn` (writes flag `Mn`, shows the real state of `Qn`)
- one **binary sensor** per digital input: `I1 … In`

all grouped under one device, `LOGO! (<ip address>)`.

> **Status: early version (0.1.0).** Digital I/O only. Tested on a LOGO! 24CE (8.4) with a DM8 24 expansion: switching, readback, inputs and unavailable/recovery. Field reports welcome.

---

## 1. Prepare the LOGO! in Soft Comfort

### 1.1 Enable the Modbus server

1. Open your program in **LOGO! Soft Comfort 8.x**.
2. Switch to **Diagram Mode**. *Tools → Ethernet Connections* is greyed out in the **Network Project** view; it is only available in Diagram Mode.
3. Open **Tools → Ethernet Connections**.
4. Under **Module Address**, enter the LOGO!'s *real* IP address, subnet mask and default gateway. If you leave other values here, uploading the program may overwrite the device's network settings.
5. Right-click **Ethernet Connections** → add a **Server connection** and choose **Modbus**.
   Use TCP port **502** and allow connections from the partner (Home Assistant), either from any address or from your HA host's IP.
   *The exact checkbox labels differ slightly between Soft Comfort versions and have not been verified for this README; check the Soft Comfort online help if unsure.*
6. Click OK.

Settings under *Remote access*, the LOGO! App or the web server have **nothing to do with Modbus** and can stay as they are.

### 1.2 Program: one OR block per output

Home Assistant never writes `Q` directly. It writes a **flag** `Mn`, and your program decides what that means:

```
 Mn ──────────┐
              ├─ OR ── Qn
 your logic ──┘
```

For each output you want to control from HA (`Q1 … Qn`):

- put an **OR** block in front of `Qn`,
- connect flag `Mn` to one input (same number: `M1 → Q1`, `M2 → Q2`, …),
- connect your existing physical logic (buttons, timers …) to the other input.

Rules for the flag `Mn`:

- its own input stays **unconnected**,
- do **not** use `Mn` as an output anywhere else in the program — otherwise the program overwrites it every cycle and the switch in HA has no effect.

Upload the program, then switch the LOGO! **STOP → RUN**.

### 1.3 Address map (for reference)

Wire addresses are 0-based; Siemens documentation lists them 1-based (+1).

| LOGO! | Modbus function | Documented | Wire address | Used as |
|---|---|---|---|---|
| I1–I24 | discrete input (FC 02) | 1–24 | 0–23 | binary sensor state |
| Q1–Q20 | coil (FC 01) | 8193–8212 | 8192–8211 | switch state (read only) |
| M1–M64 | coil (FC 05) | 8257–8320 | 8256–8319 | switch command (M1–M20) |

## 2. Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories**.
2. Repository: `https://github.com/sziszi21/ha-logo-modbus`, category **Integration**.
3. Install **Siemens LOGO! Modbus TCP**, then **restart Home Assistant**.

### Manual

Copy `custom_components/logo_modbus` into `<config>/custom_components/`, then restart Home Assistant.

Requires Home Assistant **2025.2** or newer. No extra Python packages are installed.

## 3. Add the device

*Settings → Devices & services → Add integration → **Siemens LOGO! Modbus TCP***

| Field | Default | Range | Meaning |
|---|---|---|---|
| Host | – | – | IP address of the LOGO! |
| Port | 502 | 1–65535 | Modbus TCP port |
| Number of outputs (Q) | 8 | 0–20 | creates switches `Q1…Qn` |
| Number of inputs (I) | 8 | 0–24 | creates binary sensors `I1…In` |
| Polling interval | 2 s | 1–60 s | how often Q and I are read |

The integration connects and reads `I1` before saving; if this fails you get **Failed to connect**.

Counts and polling interval can be changed later with **Configure**; the entry reloads and entities are added or removed.

Add the integration once per LOGO! (one entry per IP/port).

## 4. How it behaves

- **Switch on/off** writes flag `Mn` (FC 05). The switch state is always the **real** state of `Qn`, read by polling — not an assumed state. After a write the state is refreshed immediately.
- **OR behaviour:** if your physical logic keeps `Qn` on, switching off in HA only clears `Mn`. `Qn` stays on and the switch in HA jumps back to *on*. This is intended: HA shows what the output really does. (If you need HA to be able to force an output off, build it in the program, e.g. with separate set/reset flags and an RS block — not implemented by this integration.)
- **Power loss:** flags are non-retentive by default, so after a LOGO! restart `Mn` is 0 and HA simply shows the real `Qn`. State never drifts.
- **Unavailable:** if the LOGO! cannot be reached, all its entities become *unavailable* and recover on their own when it is back.
- **Delay:** changes made on the LOGO! side (buttons, inputs) appear in HA within one polling interval.

## 5. Practical notes

- **Pushbuttons:** for a light that should toggle both from a wall button and HA, use a pulse relay (*impulse relay*) block in the program, with the button and the flag pulse as inputs — or keep the simple OR and accept the behaviour above.
- **Transistor outputs** (e.g. DM8 24, Q5–Q8): 24 V DC, 0.3 A, positive switching. For 230 V loads use an interposing relay, with a **flyback diode** across its coil. The 24 V supply and the module share a common M (0 V).
- **Connection limit:** the LOGO! accepts only a few simultaneous Modbus/S7 connections. Soft Comfort online mode, an HMI, Node-RED etc. each use one. This integration keeps a single connection open.
- **Existing `modbus:` YAML:** this integration does not touch your configuration. You can keep a YAML `modbus:` hub (also for other devices) — but don't poll the same LOGO! from both for long, to save connections.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| *Failed to connect* | IP correct? Ping the LOGO! from the HA host. Modbus server connection configured and **uploaded**? LOGO! in RUN? Port 502 not blocked? |
| Switch does nothing | Is `Mn` wired into an OR before `Qn`? Is `Mn` written by anything else in the program? |
| Wrong output switches | Number mismatch between flag and output in the program (`M1 → Q1`). The integration uses Q1 = coil 8192, M1 = coil 8256. |
| Switch jumps back on | Physical logic keeps `Qn` on (see OR behaviour). |
| Entities unavailable at times | Too many connections to the LOGO! (Soft Comfort online, other clients); network issues. |

Enable debug logs:

```yaml
logger:
  logs:
    custom_components.logo_modbus: debug
```

## 7. Limitations

- Digital I/O only: `I1–I24`, `Q1–Q20` (via `M1–M20`).
- No analog inputs/outputs, VM/VW memory, network I/O.
- One request at a time per LOGO!; no Modbus RTU.

## License

MIT — see [LICENSE](LICENSE).
