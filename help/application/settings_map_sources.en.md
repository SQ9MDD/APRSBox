# Map sources

This panel manages the tile sources available to APRSBox maps, their order, default selection, and optional local cache.

## Source list

- Arrow buttons change the order in which sources are presented.
- The star makes an enabled source the default.
- The pencil opens a source for editing.
- The trash button removes a source. The only source and the current default cannot be deleted.
- The broom clears locally cached tiles for that source without deleting its configuration.

## Source fields

- `Name` is the label displayed in the map selector.
- `URL template` must be a standard Leaflet tile URL with `{z}`, `{x}`, and `{y}`, for example `https://server/{z}/{x}/{y}.png`.
- `Attribution` contains the map provider credit required on the map.
- `Min zoom` and `Max zoom` limit the available zoom range.
- `Notes` are stored with the source for administrators.
- `Enabled` makes the source available to maps.
- `Enable local cache/proxy` routes tile requests through APRSBox and stores downloaded tiles locally.
- `Set as default` selects this source when a map has no other saved selection.

Only standard Leaflet raster tile providers are supported here. Verify the provider's usage limits, attribution rules, and permission for proxy caching before enabling it. A useful starting point is the [Switch2OSM provider list](https://switch2osm.org/providers/#Allows-free-usage).
