# Changelog

## 1.8.43.dev - 2026-06-21
- `Traffic Monitor / KISS RX`: leere KISS-Datenframes (`0x00` ohne Payload) von TCP/IP-TNCs werden jetzt ignoriert, sodass der Traffic Monitor kein Rauschen vom Typ `AX.25 decode failed (payload too short (0B))` mehr zwischen gueltigen Paketen anzeigt.
- `Changelog / I18N`: eine deutsche Changelog-Datei und die `DE`-Auswahl anhand der aktuellen GUI-Sprache wurden hinzugefuegt.

### Hinweise
- Aeltere Eintraege sind noch nicht ins Deutsche uebersetzt.
