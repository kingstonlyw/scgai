import os
import json
import math
import time
import streamlit as st
import folium
from folium.plugins import MarkerCluster, MiniMap, Fullscreen
from geopy.distance import geodesic
import osmnx as ox
import google.generativeai as genai
from streamlit.components.v1 import html as st_html

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

st.set_page_config(page_title="POI Analyzer", layout="wide")

st.title("Property POI Analyzer")

if "summary_payload" not in st.session_state:
    st.session_state["summary_payload"] = None
if "summary_text" not in st.session_state:
    st.session_state["summary_text"] = None
if "location_str" not in st.session_state:
    st.session_state["location_str"] = None

if "pois" not in st.session_state:
    st.session_state["pois"] = None
if "center_lat" not in st.session_state:
    st.session_state["center_lat"] = None
if "center_lon" not in st.session_state:
    st.session_state["center_lon"] = None
if "radius_miles" not in st.session_state:
    st.session_state["radius_miles"] = None
if "radius_meters" not in st.session_state:
    st.session_state["radius_meters"] = None

def format_distance(mi):
    return "<0.1 mi" if mi < 0.1 else f"{mi:.1f} mi"

def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))

def miles_between(a, b):
    return haversine_miles(a[0], a[1], b[0], b[1])

default_prompt = (
    "I want to buy a property of type housing at 2575 McKinnon Street, "
    "Dallas, TX 75201 within 3 mile."
)

user_prompt = st.text_area(
    "Describe the property and radius you care about:",
    value=default_prompt,
    height=100,
)

run_button = st.button("Run analysis")


tag_map = {
    "park": {"leisure": "park"},
    "school": {"amenity": "school"},
    "university": {"amenity": "university"},
    "hospital": {"amenity": "hospital"},
    "clinic": {"amenity": "clinic"},
    "transit_station": {"public_transport": "station"},
    "bus_stop": {"highway": "bus_stop"},
    "supermarket": {"shop": "supermarket"},
    "pharmacy": {"amenity": "pharmacy"},
    "library": {"amenity": "library"},
    "restaurant": {"amenity": "restaurant"},
    "bank": {"amenity": "bank"},
    "sports_centre": {"leisure": "sports_centre"},
    "place_of_worship": {"amenity": "place_of_worship"},
    "parking": {"amenity": "parking"},
    "fuel": {"amenity": "fuel"},
    "residential": {"landuse": "residential"},
    "industrial": {"landuse": "industrial"},
    "construction": {"landuse": "construction"},
    "landfill": {"landuse": "landfill"},
    "highway": {"highway": ["motorway", "motorway_link", "trunk", "trunk_link"]},
    "waste_disposal": {"amenity": "waste_disposal"},
    "power_station": {"power": "plant"},
}

positive_categories = [
    "park","school","university","hospital","clinic","transit_station","bus_stop",
    "supermarket","pharmacy","library","restaurant","cafe","bank","playground",
    "sports_centre","place_of_worship","parking","fuel","railway","residential"
]
negative_categories = [
    "industrial","construction","landfill","highway","waste_disposal",
    "quarry","power_station","noise_barrier"
]

icon_map = {
    "park": ("tree", "green"),
    "school": ("graduation-cap", "blue"),
    "university": ("graduation-cap", "darkblue"),
    "hospital": ("plus-sign", "red"),
    "clinic": ("medkit", "red"),
    "transit_station": ("train", "cadetblue"),
    "bus_stop": ("bus", "lightblue"),
    "supermarket": ("shopping-cart", "darkgreen"),
    "pharmacy": ("medkit", "lightred"),
    "library": ("book", "purple"),
    "restaurant": ("cutlery", "orange"),
    "cafe": ("coffee", "beige"),
    "bank": ("usd", "darkpurple"),
    "playground": ("child", "lightgreen"),
    "sports_centre": ("flag", "darkgreen"),
    "place_of_worship": ("star", "gray"),
    "parking": ("road", "lightgray"),
    "fuel": ("tint", "darkred"),
    "residential": ("home", "lightgray"),
    "industrial": ("industry", "black"),
    "construction": ("wrench", "gray"),
    "landfill": ("trash", "gray"),
    "highway": ("road", "darkgray"),
    "waste_disposal": ("trash", "darkgray"),
    "power_station": ("flash", "black"),
}

def within_radius(center, point, miles):
    try:
        lat1, lon1 = center
        lat2, lon2 = point
        return haversine_miles(lat1, lon1, lat2, lon2) <= miles
    except Exception:
        return False

def clean_name(row, fallback):
    n = row.get("name")
    if isinstance(n, str) and n.strip():
        return n.strip()
    b = row.get("brand")
    if isinstance(b, str) and b.strip():
        return b.strip()
    return fallback

def extract_address(row, coords=None):
    housenumber = row.get("addr:housenumber") or row.get("addr:house_number")
    street = row.get("addr:street")
    city = row.get("addr:city") or row.get("addr:town") or row.get("addr:village")
    postcode = row.get("addr:postcode")
    full = row.get("addr:full")

    parts = []
    if isinstance(full, str) and full.strip():
        parts.append(full.strip())
    else:
        first = ""
        if isinstance(housenumber, str) and housenumber.strip():
            first = housenumber.strip()
        if isinstance(street, str) and street.strip():
            if first:
                first = first + " " + street.strip()
            else:
                first = street.strip()
        if first:
            parts.append(first)
        if isinstance(city, str) and city.strip():
            parts.append(city.strip())
        if isinstance(postcode, str) and postcode.strip():
            parts.append(postcode.strip())

    if parts:
        return ", ".join(parts)

    if coords is not None:
        lat_c, lon_c = coords
        return f"{lat_c:.5f}, {lon_c:.5f}"

    return "Address not available"

def dedup_by_location(pois, threshold_meters=40.0):
    merged = []
    for p in sorted(pois, key=lambda x: x["distance_miles"]):
        latp, lonp = p["coordinates"]
        found = False
        for m in merged:
            d = haversine_miles(latp, lonp, m["coordinates"][0], m["coordinates"][1]) * 1609.34
            if d <= threshold_meters:
                m["categories"].add(p["category"])
                m["types"].add(p["type"])
                if not m["name"] and p["name"]:
                    m["name"] = p["name"]
                if not m.get("address") and p.get("address"):
                    m["address"] = p["address"]
                found = True
                break
        if not found:
            m = p.copy()
            m["categories"] = {p["category"]}
            m["types"] = {p["type"]}
            merged.append(m)
    for m in merged:
        m["categories"] = sorted(list(m["categories"]))
        m["types"] = sorted(list(m["types"]))
    return merged

def icon_for(category, default_color):
    name, color = icon_map.get(category, ("info-sign", default_color))
    return folium.Icon(icon=name, color=color)

headline_groups = {
    "Daily convenience (supermarkets, cafes, banks)": [
        "supermarket", "pharmacy", "restaurant", "cafe", "bank"
    ],
    "Schools & parks": [
        "school", "university", "playground", "park", "library"
    ],
    "Transit access": [
        "transit_station", "bus_stop", "railway"
    ],
    "Nuisance / industrial": [
        "industrial", "construction", "landfill", "quarry",
        "power_station", "highway", "waste_disposal", "noise_barrier"
    ],
}

def parse_json_block(text):
    try:
        return json.loads(text)
    except Exception:
        pass
    if "{" in text and "}" in text:
        candidate = text[text.find("{"): text.rfind("}") + 1]
        return json.loads(candidate)
    raise ValueError("Could not parse JSON from Gemini response.")


map_html = None
summary_text = None

if run_button and user_prompt.strip():
    start_time = time.time()
    progress_bar = st.progress(0)
    status_placeholder = st.empty()

    def update_progress(pct, msg):
        pct_int = max(0, min(int(pct), 100))
        elapsed = time.time() - start_time

        if pct_int > 0 and elapsed > 0.2:
            est_total = elapsed * 100.0 / pct_int
            est_remaining = max(est_total - elapsed, 0.0) + 12
            status_placeholder.write(
                f"{msg}  |  Elapsed: {elapsed:.1f}s  |  Est. remaining: ~{est_remaining:.1f}s"
            )
        else:
            status_placeholder.write(
                f"{msg}  |  Elapsed: {elapsed:.1f}s"
            )

        progress_bar.progress(pct_int)

    update_progress(5, "Starting analysis")

    model = genai.GenerativeModel("gemini-2.5-flash")
    update_progress(10, "Parsing your input with Gemini")

    response = model.generate_content(
        """
        Return ONLY valid JSON using this schema:
        {
          "type": "<property type>",
          "address": "<full address>",
          "radius_miles": <numeric radius in miles>
        }
        If radius is missing, default to 1.0.
        """ + user_prompt
    )

    raw_text = response.text.strip()
    parsed = parse_json_block(raw_text)

    location = parsed.get("address", "unknown address")
    property_type = parsed.get("type", "unknown")
    radius_miles = float(parsed.get("radius_miles", 1.0))
    radius_meters = radius_miles * 1609.34

    update_progress(20, "Geocoding address")
    lat, lon = ox.geocode(location)

    all_pois = []
    total_categories = len(positive_categories) + len(negative_categories)
    processed_categories = 0

    update_progress(30, "Collecting points of interest from OpenStreetMap")

    for category_list, label in [(positive_categories, "positive"), (negative_categories, "negative")]:
        for category in category_list:
            try:
                tags = tag_map[category]
                gdf = ox.features_from_point((lat, lon), tags=tags, dist=radius_meters)
                if gdf.empty:
                    processed_categories += 1
                    progress_pct = 30 + int(40 * processed_categories / total_categories)
                    update_progress(progress_pct, "Collecting points of interest from OpenStreetMap")
                    continue
                gdf = gdf.dropna(subset=["geometry"])
                for _, row in gdf.iterrows():
                    geom = row.geometry
                    if geom.is_empty:
                        continue
                    centroid = geom.centroid
                    if centroid.is_empty or any(math.isnan(v) for v in [centroid.x, centroid.y]):
                        continue
                    coords = (centroid.y, centroid.x)
                    if not within_radius((lat, lon), coords, radius_miles):
                        continue
                    place_name = clean_name(row, category)
                    dist_mi = round(haversine_miles(lat, lon, coords[0], coords[1]), 3)

                    address_str = extract_address(row, coords)

                    all_pois.append({
                        "name": place_name,
                        "type": label,
                        "category": category,
                        "distance_miles": dist_mi,
                        "coordinates": [coords[0], coords[1]],
                        "brand": row.get("brand"),
                        "osm_id": row.get("osmid"),
                        "address": address_str,
                    })
            except Exception:
                pass
            finally:
                processed_categories += 1
                progress_pct = 30 + int(40 * processed_categories / total_categories)
                update_progress(progress_pct, "Collecting points of interest from OpenStreetMap")

    update_progress(75, "Cleaning and organizing POIs")

    all_pois = dedup_by_location(all_pois, threshold_meters=40.0)

    MAX_PER_CATEGORY = 25
    by_cat = {}
    filtered = []
    for p in sorted(all_pois, key=lambda x: (x["type"], x["category"], x["distance_miles"])):
        c = p["category"]
        by_cat[c] = by_cat.get(c, 0) + 1
        if by_cat[c] <= MAX_PER_CATEGORY:
            filtered.append(p)

    category_counts = {}
    for p in filtered:
        cat = p["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    headline_counts = {}
    for label, cats in headline_groups.items():
        headline_counts[label] = sum(category_counts.get(c, 0) for c in cats)

    poi_data = {
        "location": location,
        "radius_miles": radius_miles,
        "POIs": filtered,
    }
    with open("poi_analysis.json", "w") as f:
        json.dump(poi_data, f, indent=2)

    # store everything needed for map + summary in session_state
    st.session_state["pois"] = filtered
    st.session_state["center_lat"] = lat
    st.session_state["center_lon"] = lon
    st.session_state["radius_miles"] = radius_miles
    st.session_state["radius_meters"] = radius_meters
    st.session_state["location_str"] = location

    update_progress(90, "Preparing summary of pros and cons")

    positive_pois = [p for p in filtered if p["type"] == "positive"]
    negative_pois = [p for p in filtered if p["type"] == "negative"]

    summary_payload = {
        "property_type": property_type,
        "location": location,
        "radius_miles": radius_miles,
        "positive_pois": positive_pois,
        "negative_pois": negative_pois,
    }

    st.session_state["summary_payload"] = summary_payload

    summary_response = model.generate_content(
        """
        You are helping evaluate locations for property acquisition.

        For ALL distances in the JSON below:
        - Round distance_miles to ONE decimal place (0.1 mi).
        - If a value is below 0.1 miles, refer to it as "<0.1 miles".

        Given the JSON, identify:
        1) The most important POSITIVE points of interest for this property type.
        2) The most important NEGATIVE points of interest or risks.
        3) A short, practical summary (3–5 sentences) of how attractive this location is.

        Focus on the relevance of each POI to the property type and its distance.

        Return a concise, human-readable explanation, not JSON.
        """ + "\n\nJSON:\n" + json.dumps(summary_payload, indent=2)
    )

    st.session_state["summary_text"] = summary_response.text

    update_progress(100, "Analysis complete")

    st.subheader("Parsed input")
    st.write(f"**Property type:** {property_type}")
    st.write(f"**Location:** {location}")
    st.write(f"**Radius:** {radius_miles} miles")

if st.session_state["pois"] is not None:
    poi_query = st.text_input(
        "Filter POIs on map (e.g., 'restaurant', 'school', 'park')",
        value="",
        placeholder="Type to filter what appears on the map..."
    ).strip().lower()

    pois = st.session_state["pois"]
    lat = st.session_state["center_lat"]
    lon = st.session_state["center_lon"]
    radius_miles = st.session_state["radius_miles"]
    radius_meters = st.session_state["radius_meters"]

    if poi_query:
        filtered_for_map = [
            p for p in pois
            if poi_query in p["name"].lower()
            or poi_query in p["category"].lower()
            or poi_query in p["type"].lower()
        ]
    else:
        filtered_for_map = pois

    category_counts = {}
    for p in filtered_for_map:
        cat = p["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    headline_counts = {}
    for label, cats in headline_groups.items():
        headline_counts[label] = sum(category_counts.get(c, 0) for c in cats)

    m = folium.Map(location=[lat, lon], zoom_start=15, control_scale=True, tiles=None)

    folium.TileLayer("OpenStreetMap", name="Streets").add_to(m)
    folium.TileLayer("CartoDB positron", name="Light").add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite"
    ).add_to(m)

    radius_circle = folium.Circle(
        location=[lat, lon],
        radius=radius_meters,
        fill=False,
        color="#2563eb",
        weight=2,
        opacity=0.7,
    )
    radius_circle.add_to(m)
    folium.Marker(
        [lat + 0.0009, lon],
        icon=folium.DivIcon(
            html=f"<div style='font-size:12px;color:#2563eb;'>Radius: {radius_miles} mi</div>"
        )
    ).add_to(m)

    location = st.session_state["location_str"] or "Unknown location"
    folium.Marker(
        [lat, lon],
        tooltip=location,
        popup=f"<b>{location}</b>",
        icon=folium.Icon(color="blue", icon="star")
    ).add_to(m)

    SINGLETON_CATEGORIES = {"parking", "highway", "bus_stop", "playground", "park", "residential", "construction", "cafe"}   # only show ONE marker total
    category_clusters = {}
    singleton_added = set()

    for p in filtered_for_map:
        cat = p["category"]
        name = p["name"]
        dist = p["distance_miles"]
        coords = p["coordinates"]
        address_str = p.get("address") or "Address not available"

        formatted_dist = format_distance(dist)

        popup_html = (
            f"<b>{name}</b>"
            f"<br><i>{address_str}</i>"
            f"<br>Category: {cat}"
            f"<br>Distance: {formatted_dist}"
        )

        tooltip_text = f"{name} — {address_str}"

        CLUSTER_RADIUS_MILES = 0.25

        if cat in SINGLETON_CATEGORIES:
            if cat not in category_clusters:
                category_clusters[cat] = []

            assigned = False
            for rep in category_clusters[cat]:
                if miles_between(coords, rep) <= CLUSTER_RADIUS_MILES:
                    assigned = True
                    break

            if not assigned:
                category_clusters[cat].append(coords)

                icon = folium.Icon(
                    color="gray",
                    icon="road" if cat == "highway" else "parking"
                )

                folium.Marker(
                    location=coords,
                    tooltip=f"{cat.title()} cluster (~0.25 mi radius)",
                    popup=folium.Popup(
                        f"<b>{cat.title()}</b><br>Represents multiple locations within 0.25 miles.",
                        max_width=260
                    ),
                    icon=icon,
                ).add_to(m)

            continue

        if cat not in category_clusters:
            category_clusters[cat] = MarkerCluster(
                name=cat,
                options={
                    "spiderfyOnMaxZoom": True,
                    "showCoverageOnHover": False,
                    "disableClusteringAtZoom": 17
                }
            )
            category_clusters[cat].add_to(m)

        if poi_query:
            icon = folium.Icon(color="yellow", icon="info-sign")
        else:
            icon = icon_for(cat, default_color=("green" if p["type"] == "positive" else "red"))

        marker = folium.Marker(
            location=coords,
            tooltip=tooltip_text,
            popup=folium.Popup(popup_html, max_width=260),
            icon=icon,
        )

        marker.add_to(category_clusters[cat])



    headline_html_lines = ""
    for label, count in headline_counts.items():
        headline_html_lines += f"<br><b>{label}:</b> {count}"

    legend_html = f"""
    <div style="
    position:absolute;
    top:10px;
    left:10px;
    z-index:999999;
    background-color:white;
    padding:10px;
    border:1px solid #ccc;
    border-radius:6px;
    font-size:12px;
    box-shadow:0px 2px 6px rgba(0,0,0,0.3);
    ">
    <b>Legend</b><br>
    <span style='color:green;'>●</span> Positive<br>
    <span style='color:red;'>●</span> Negative<br>
    <br><b>Category counts</b><br>
    {headline_html_lines}
    </div>
    """

    legend_pane = folium.map.CustomPane("floating-legend")
    m.add_child(legend_pane)
    legend_pane.add_child(folium.Element(legend_html))

    MiniMap(toggle_display=True).add_to(m)
    Fullscreen().add_to(m)
    folium.LayerControl(position="topright").add_to(m)

    map_html = m._repr_html_()

    st.subheader("Map")
    st_html(map_html, height=600, scrolling=False)


if st.session_state["summary_payload"] is not None:
    reload_summary = st.button("Reload summary only")

    if reload_summary:
        model = genai.GenerativeModel("gemini-2.5-flash")
        new_response = model.generate_content(
            """
                You are helping evaluate locations for property acquisition.

                For ALL distances in the JSON below:
                - Round distance_miles to ONE decimal place (0.1 mi).
                - If a value is below 0.1 miles, refer to it as "<0.1 miles".

                Given the JSON, identify:
                1) The most important POSITIVE points of interest for this property type.
                2) The most important NEGATIVE points of interest or risks.
                3) A short, practical summary (3–5 sentences) of how attractive this location is.

                Focus on the relevance of each POI to the property type and its distance.

                Return a concise, human-readable explanation, not JSON.
            """ + "\n\nJSON:\n" + json.dumps(summary_payload, indent=2)
        )
        st.session_state["summary_text"] = new_response.text

    loc_label = st.session_state["location_str"] or "Unknown location"
    st.subheader(f"Location Summary: {loc_label}")
    st.write("Powered by Gemini")
    st.write(st.session_state["summary_text"])
