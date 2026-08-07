# APRS emergency alerts

The `Alerts` tab shows logical alerts created from native APRS emergency frames and CAWF or `NWS-WARN` group messages. They all enter the same list and provide details, frame history, muting, and deletion.

`NWS-WARN` receives compact U.S. county weather warnings. Alert details include the event, level, expiry, and UGC area codes, and APRSBox highlights recognized counties on the map. This is a receive-only profile: APRSBox cannot send or cancel a `NWS-WARN` alert. Group setup, frame format, levels, area mapping, and limitations are covered in the [detailed NWS-WARN guide](settings_alarms_nws_warn.en.md).

A CAWF alert sent from the APRSBox form also enters this list and behaves like every other alert.

When a CAWF alert's full source callsign exactly matches the configured station callsign, the list shows a `Cancel alarm` action. After confirmation, APRSBox stops repeats and sends a CAWF `CANCEL` frame with the same source, group, and logical `ALERT_ID`.

The `Send alarm` button next to `Delete selected` opens a separate composer page. In the form, `Path (RF)` selects the path used for radio transmission. The station's configured path is selected by default. `Direct (no path)` transmits without digipeater hops. The selected path is stored with the alert and remains unchanged for repeats and the `CANCEL` frame. It does not select an APRS-IS server route.

- Clicking a row opens the modal with the latest alert frame.
- The alert details button opens the complete record and related frame history.
- Muting does not stop alert updates or the frame counter.
- Deleting an alert does not delete the original Traffic Monitor frames.

## Browser alarm sound

Browsers may block automatic audio playback by default. In that case the alert modal appears correctly, but the sound starts only after a click on the page.

On the computer displaying APRSBox:

1. Open the site permissions next to the address bar.
2. Find the `Autoplay` setting.
3. Select `Allow audio and video`, or the equivalent option that permits sound.
4. Reload the APRSBox tab.

This permission must be configured in the browser on the display computer. The APRSBox server may run on a different device.

Also verify that the tab, browser, and operating system are not muted and that the correct audio output is selected.

After autoplay is allowed, an unmuted frame selected for an alert popup opens the modal and starts the sound without an additional click. This also applies to `NWS-WARN` when its category and level meet the configured popup threshold. A muted alert continues to update but intentionally remains silent.

## Muting

Alerts can be muted for `1 hour`, `4 hours`, `24 hours`, or indefinitely. After a timed mute expires, only a subsequent frame for that alert can open the modal and start the sound.

## Deleting

Deleting removes the logical alert record and its relations. Original frames remain in Traffic Monitor. A subsequent matching frame may create the alert again.
