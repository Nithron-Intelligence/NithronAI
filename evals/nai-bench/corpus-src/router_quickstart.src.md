---
out: Handbuecher/NetHaven_AX3000_quickstart.md
format: text
language: en
kind: manual
license: CC0-1.0
source: written for nai-bench (fictional brand and product)
provenance: claude-authored
---
# NetHaven AX3000 – Quick Start Guide

## What's in the box

- NetHaven AX3000 Wi-Fi 6 router
- 12 V power adapter
- 1 m Ethernet cable

## Set up

1. Connect the **WAN** port (blue) to your modem or fibre terminal.
2. Plug in the power adapter and wait until the status LED is solid white (about 2 minutes).
3. Connect to the Wi-Fi network printed on the sticker on the underside, or plug a computer into one of the four yellow LAN ports.
4. Open a browser and go to `http://192.168.8.1` (or `http://nethaven.home`). This is the router's default IP address.
5. Log in with the admin password printed on the sticker and follow the setup wizard. You will be asked to choose a new admin password.

## Guest network

The guest network is switched off by default. Switch it on in the NetHaven app under **Wi-Fi → Guest network**. You choose its name and password there; guests cannot reach devices on your home network.

## Firmware updates

Automatic updates are on by default and are installed at 03:00 local time when no device is streaming. You can change the time under **System → Updates**.

## Factory reset

With the router switched on, press and hold the **RESET** button on the back for 10 seconds until the status LED flashes red. The router restarts with the default settings (IP address 192.168.8.1, admin password from the sticker). All your settings are deleted.

## Status LED

| LED | Meaning |
|---|---|
| Solid white | Online |
| Pulsing white | Starting up or updating |
| Solid orange | No internet connection on the WAN port |
| Flashing red | Factory reset in progress |
