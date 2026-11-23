# Home network notes (Jonas)

Router: OpenWrt on the hallway router, admin UI only from VLAN 10.

| VLAN | Name | Subnet | DHCP range | Notes |
|---|---|---|---|---|
| 10 | home | 192.168.10.0/24 | .100–.199 | laptops, phones, NAS at 192.168.10.20 (static) |
| 20 | iot | 192.168.20.0/24 | .50–.150 | heating thermostat, washer-dryer, TV; no access to VLAN 10 |
| 30 | guest | 192.168.30.0/24 | .10–.60 | internet only, password changes on the 1st of each month |

```
# /etc/config/firewall excerpt
config forwarding
    option src 'home'
    option dest 'iot'
```

The NAS web UI is reachable as https://nas.home.example from VLAN 10 only. Remote access only through the
WireGuard tunnel (port 51820/udp), never by port forwarding.
