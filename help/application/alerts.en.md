# APRS emergency alerts

The `Alerts` tab shows logical alerts created from received APRS emergency frames. Subsequent frames from the same full source callsign update one alert and its history.

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
