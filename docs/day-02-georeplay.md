# Day 2: GeoReplay

## Problem Card

Control tower teams often receive GPS pings and site/geofence masters as separate files. The raw dots do not immediately answer the operational questions managers ask:

- Did the vehicle enter the planned depot, hub, or customer site?
- When did it arrive and leave?
- How long did it dwell?
- Which planned stops were missed?
- Which visits were not in the plan?

## Stakeholder

- Control tower analyst
- Dispatch manager
- Fleet operations manager
- Transport manager

## Input Contract

GeoReplay accepts:

- `gps_points.csv`: `vehicle_id`, `timestamp`, `lat`, `lon`, optional `speed_kph`
- `geofences.csv`: `geofence_id`, `name`, `lat`, `lon`, `radius_m`, optional `geofence_type`
- `planned_stops.csv`: optional plan with `vehicle_id`, `geofence_id`, optional `planned_arrival`, `stop_sequence`

## Core Logic

The app uses deterministic geospatial logic:

- Convert GPS pings and circle geofences into GeoPandas/Shapely geometries.
- Detect pings inside geofence polygons.
- Reconstruct visit events by vehicle and geofence.
- Calculate dwell time from first inside ping to last inside ping.
- Flag missed planned stops.
- Flag unexpected geofence visits.
- Flag long dwell based on the configured threshold.

## Output

GeoReplay writes:

- `georeplay/output/visit_events.csv`
- `georeplay/output/exceptions.csv`

The Streamlit app also shows:

- Visit event table
- Exception table
- Interactive Folium map with pings, geofences, and reconstructed visits

## Geocoding Rule

GeoReplay includes `geopy` with the free Nominatim/OpenStreetMap backend, but it does not reverse-geocode raw GPS pings.

Reverse geocoding is only available for:

- Geofence master rows
- Final visit events
- Final exception locations

The app waits 1 second between calls to respect Nominatim's free usage policy.

## Limitations

- V1 supports circular geofences from latitude, longitude, and radius.
- It is local-first and file-based; there are no live tracking integrations.
- Sparse GPS data can understate dwell or miss a short visit.
- Missed-stop detection is deterministic and should be reviewed when GPS coverage is weak.
- No AI, route optimization, customer messaging, or paid APIs are included.

## Public Learning

Raw GPS pings are not an operations product. Visit events are the useful layer: entry, exit, dwell, missed stop, and unexpected stop.
