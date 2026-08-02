# APRS emergency alerts

The `Alerts` tab shows logical alerts created from APRS emergency and CAWF frames. A CAWF alert sent from the APRSBox form enters the same list and behaves like every other alert, including normal details, frame history, muting, and deletion.

When the alert's full source callsign exactly matches the configured station callsign, the list shows a `Cancel alarm` action. After confirmation, APRSBox stops repeats and sends a CAWF `CANCEL` frame with the same source, group, and logical `ALERT_ID`.

The `Send alarm` button next to `Delete selected` opens a separate composer page. In the form, `Path (RF)` selects the path used for radio transmission. The station's configured path is selected by default. `Direct (no path)` transmits without digipeater hops. The selected path is stored with the alert and remains unchanged for repeats and the `CANCEL` frame. It does not select an APRS-IS server route.

- Clicking a row opens the modal with the latest emergency frame.
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

After autoplay is allowed, an unmuted emergency frame opens the modal and starts the sound without an additional click. A muted alert continues to update but intentionally remains silent.

## Muting

Alerts can be muted for `1 hour`, `4 hours`, `24 hours`, or indefinitely. After a timed mute expires, only a subsequent emergency frame can open the modal and start the sound.

## Deleting

Deleting removes the logical alert record and its relations. Original frames remain in Traffic Monitor. The next emergency frame from that source creates a new alert.
