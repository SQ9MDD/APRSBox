# APRS ghum SeHmey

panelvam APRS group message ghum receive-only channel SeH. Destination groupmey ghum mojbogh, Alerts listDaq eventmey, emergency popup, automatic APRS-IS receive filter je wIv.

## nom yIchergh

- `APRS alarms` yIchu'.
- Comma lo' groupmey yIghItlh, `PL-WARN, NWS-WARN` rur.
- Event category HochvaD `Alerts` `Alert popup` thresholds yIwIv.
- yIpol, vaj effective RF groups automatic APRS-IS filter je yIlegh.

Group pongDaq 1–9 uppercase letters, digits, hyphenmey neH chaw'lu'. Lowercase uppercase moj, duplicate teq, `BLN...` bulletin address lajbe'.

## Frame He

- Configured alarm groupDaq message jaHchugh neH alarm path lo'.
- Event pong category wIv: tornado, thunderstorm, flood, wind, heat, pagh `Other / unknown`.
- Event code taghHa' digits severity moj.
- `Alerts` Alerts list record chenmoH pagh update.
- `Alert popup` alarm frame wa'DIch global popup chaw' pagh bot.
- Map pageDaq map layer visibility control pIm tu'lu'; area code HochvaD local geometry nIS.

Number threshold levelvetlh je levelmey jen laj. `Off` category chu'Ha'. Unknown severity category chu'ta'chugh pol, format chu' pagh QIH cichoH Qaw'be'meH; yellow/orange/red classification Hutlh 'ej geometry tu'lu'chugh gray 'ang.

## Warning formatmey

- [CAWF guide](settings_alarms_cawf.tlh.md) — `PL-WARN` rur country profiles, multipart alerts, geometry, lifecycle, trust je.
- [NWS-WARN guide](settings_alarms_nws_warn.tlh.md) — U.S. county warning, UGC codes, map coverage, APRSBox limits je.
- [Alerts list, mute, delete](alerts.en.md) — alarm lajlu'DI' operator actions.

## Limits potlh

- Switch configured alarm groups neH SeH. Native APRS emergency Mic-E emergency frames shared Alerts system lo' independently.
- Alarm-group messages normal conversationsDaq chelbe', normal message notifications triggerbe', APRS ACK notlhbe'.
- APRSBox warning publisher authenticatebe' 'ej trusted-sender allowlist ghajbe'. APRS-IS reception official proof 'oHbe'.
- `DDHHMMz` expiry QIH pagh Hutlhchugh automatic expiry chenbe'; record active ratlhlaH replace pagh operator delete tlhIngan.
