from __future__ import annotations


# Descriptions from the machine-readable aprs.fi APRS symbol index:
# https://github.com/hessu/aprs-symbol-index (CC BY-SA 4.0).
# Tuple positions map directly to printable APRS symbol codes 33 (!) through 126 (~).
_PRIMARY_DESCRIPTIONS = (
    "Police station", "", "Digipeater", "Telephone", "DX cluster", "HF gateway",
    "Small aircraft", "Mobile satellite station", "Wheelchair, handicapped", "Snowmobile",
    "Red Cross", "Boy Scouts", "House", "Red X", "Red dot",
    "Numbered circle: 0", "Numbered circle: 1", "Numbered circle: 2", "Numbered circle: 3",
    "Numbered circle: 4", "Numbered circle: 5", "Numbered circle: 6", "Numbered circle: 7",
    "Numbered circle: 8", "Numbered circle: 9", "Fire", "Campground, tent", "Motorcycle",
    "Railroad engine", "Car", "File server", "Hurricane predicted path", "Aid station", "BBS",
    "Canoe", "", "Eyeball", "Farm vehicle, tractor", "Grid square, 3 by 3", "Hotel",
    "TCP/IP network station", "", "School", "PC user", "Mac apple", "NTS station", "Balloon",
    "Police car", "", "Recreational vehicle", "Space Shuttle", "SSTV", "Bus",
    "ATV, Amateur Television", "Weather service site", "Helicopter", "Sailboat", "Windows flag",
    "Human", "DF triangle", "Mailbox, post office", "Large aircraft", "Weather station",
    "Satellite dish antenna", "Ambulance", "Bicycle", "Incident command post", "Fire station",
    "Horse, equestrian", "Fire truck", "Glider", "Hospital", "IOTA, islands on the air", "Jeep",
    "Truck", "Laptop", "Mic-E repeater", "Node, black bulls-eye", "Emergency operations center",
    "Dog", "Grid square, 2 by 2", "Repeater tower", "Ship, power boat", "Truck stop",
    "Semi-trailer truck, 18-wheeler", "Van", "Water station", "X / Unix",
    "House, yagi antenna", "Shelter", "", "", "", "",
)

_ALTERNATE_DESCRIPTIONS = (
    "Emergency", "", "Digipeater, green star", "Bank or ATM", "", "Gateway station",
    "Crash / incident site", "Cloudy", "Firenet MEO, MODIS Earth Observation", "Snow", "Church",
    "Girl Scouts", "House, HF antenna", "Ambiguous, question mark inside circle",
    "Waypoint destination", "Circle, IRLP / Echolink/WIRES", "", "", "", "", "", "", "",
    "802.11 WiFi or other network node", "Gas station", "Hail", "Park, picnic area",
    "Advisory, single red flag", "", "Red car", "Info kiosk", "Hurricane, Tropical storm",
    "White box", "Blowing snow", "Coast Guard", "Drizzling rain", "Smoke, Chimney",
    "Freezing rain", "Snow shower", "Haze", "Rain shower", "Lightning", "Kenwood HT",
    "Lighthouse", "", "Navigation buoy", "Rocket", "Parking", "Earthquake", "Restaurant",
    "Satellite", "Thunderstorm", "Sunny", "VORTAC, Navigational aid", "NWS site", "Pharmacy",
    "", "", "Wall Cloud", "", "", "Aircraft", "Weather site", "Rain", "Red diamond",
    "Blowing dust, sand", "CD triangle, RACES, CERTS, SATERN", "DX spot", "Sleet",
    "Funnel cloud", "Gale, two red flags", "Store", "Black box, point of interest",
    "Work zone, excavating machine", "SUV, ATV", "", "Value sign, 3 digit display",
    "Red triangle", "Small circle", "Partly cloudy", "", "Restrooms", "Ship, boat", "Tornado",
    "Truck", "Van", "Flooding", "", "Skywarn", "Shelter", "Fog", "", "", "",
)


def get_aprs_symbol_description(table: str, code: str) -> str:
    if len(code) != 1:
        return ""
    index = ord(code) - 33
    if index < 0 or index >= len(_PRIMARY_DESCRIPTIONS):
        return ""
    descriptions = _ALTERNATE_DESCRIPTIONS if table == "\\" else _PRIMARY_DESCRIPTIONS
    return descriptions[index]

