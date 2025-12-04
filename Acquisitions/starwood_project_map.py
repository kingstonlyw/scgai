import os
import json
import math
import streamlit as st
import folium
from folium.plugins import MarkerCluster, MiniMap, Fullscreen
from geopy.distance import geodesic
import osmnx as ox
import google.generativeai as genai
from streamlit.components.v1 import html as st_html

# Configure Gemini
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# ---------- Streamlit UI ----------
st.set_page_config(page_title="POI Analyzer", layout="wide")

st.title("Property POI Analyzer")

default_prompt = (
    "I want to buy a property of type housing at 127 West Lane, "
    "Ridgefield, CT within 3 mile."
)

user_prompt = st.text_area(
    "Describe the property and radius you care about:",
    value=default_prompt,
    height=100,
)

run_button = st.button("Run analysis")

# We keep map_html and summary_text so we can display them
map_html = None
summary_text = None

if run_button and user_prompt.strip():
    # ---------- 1. Parse natural language with Gemini ----------
    model = genai.GenerativeModel("gemini-2.5-flash")
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

    def parse_json_block(text):
        try:
            return json.loads(text)
        except Exception:
            pass
        if "{" in text and "}" in text:
            candidate = text[text.find("{"): text.rfind("}") + 1]
            return json.loads(candidate)
        raise ValueError("Could not parse JSON from Gemini response.")

    parsed = parse_json_block(raw_text)

    location = parsed.get("address", "unknown address")
    property_type = parsed.get("type", "unknown")
    radius_miles = float(parsed.get("radius_miles", 1.0))
    radius_meters = radius_miles * 1609.34
    lat, lon = ox.geocode(location)

    # ---------- 2. POI + map analysis code (your existing logic) ----------

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
        "cafe": {"amenity": "cafe"},
        "bank": {"amenity": "bank"},
        "playground": {"leisure": "playground"},
        "sports_centre": {"leisure": "sports_centre"},
        "place_of_worship": {"amenity": "place_of_worship"},
        "parking": {"amenity": "parking"},
        "fuel": {"amenity": "fuel"},
        "railway": {"railway": True},
        "residential": {"landuse": "residential"},
        "industrial": {"landuse": "industrial"},
        "construction": {"landuse": "construction"},
        "landfill": {"landuse": "landfill"},
        "highway": {"highway": ["motorway", "motorway_link", "trunk", "trunk_link"]},
        "waste_disposal": {"amenity": "waste_disposal"},
        "quarry": {"landuse": "quarry"},
        "power_station": {"power": "plant"},
        "noise_barrier": {"barrier": "noise_barrier"},
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
        "railway": ("train", "black"),
        "residential": ("home", "lightgray"),
        "industrial": ("industry", "black"),
        "construction": ("wrench", "gray"),
        "landfill": ("trash", "gray"),
        "highway": ("road", "darkgray"),
        "waste_disposal": ("trash", "darkgray"),
        "quarry": ("warning-sign", "gray"),
        "power_station": ("flash", "black"),
        "noise_barrier": ("minus-sign", "lightgray"),
    }

    def within_radius(center, point, miles):
        try:
            return geodesic(center, point).miles <= miles
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

    def dedup_by_location(pois, threshold_meters=40.0):
        merged = []
        for p in sorted(pois, key=lambda x: x["distance_miles"]):
            latp, lonp = p["coordinates"]
            found = False
            for m in merged:
                d = geodesic((latp, lonp), (m["coordinates"][0], m["coordinates"][1])).meters
                if d <= threshold_meters:
                    m["categories"].add(p["category"])
                    m["types"].add(p["type"])
                    if not m["name"] and p["name"]:
                        m["name"] = p["name"]
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

    all_pois = []
    for category_list, label in [(positive_categories, "positive"), (negative_categories, "negative")]:
        for category in category_list:
            try:
                tags = tag_map[category]
                gdf = ox.features_from_point((lat, lon), tags=tags, dist=radius_meters)
                if gdf.empty:
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
                    dist_mi = round(geodesic((lat, lon), coords).miles, 3)
                    all_pois.append({
                        "name": place_name,
                        "type": label,
                        "category": category,
                        "distance_miles": dist_mi,
                        "coordinates": [coords[0], coords[1]],
                        "brand": row.get("brand"),
                        "osm_id": row.get("osmid"),
                    })
            except Exception:
                continue

    all_pois = dedup_by_location(all_pois, threshold_meters=40.0)

    MAX_PER_CATEGORY = 25
    by_cat = {}
    filtered = []
    for p in sorted(all_pois, key=lambda x: (x["type"], x["category"], x["distance_miles"])):
        c = p["category"]
        by_cat[c] = by_cat.get(c, 0) + 1
        if by_cat[c] <= MAX_PER_CATEGORY:
            filtered.append(p)

    # Save JSON (optional)
    poi_data = {
        "location": location,
        "radius_miles": radius_miles,
        "POIs": filtered,
    }
    with open("poi_analysis.json", "w") as f:
        json.dump(poi_data, f, indent=2)

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

    folium.Marker(
        [lat, lon],
        tooltip=location,
        popup=f"<b>{location}</b>",
        icon=folium.Icon(color="blue", icon="star")
    ).add_to(m)

    cluster_pos = MarkerCluster(name="Positive", show=True)
    cluster_neg = MarkerCluster(name="Negative", show=True)
    cluster_pos.add_to(m)
    cluster_neg.add_to(m)

    for p in filtered:
        cat = p["category"]
        name = p["name"]
        dist = p["distance_miles"]
        coords = p["coordinates"]
        popup_html = (
            f"<b>{name}</b>"
            f"<br>Category: {cat}"
            f"<br>Distance: {dist} mi"
        )
        icon = icon_for(cat, default_color=("green" if p["type"] == "positive" else "red"))
        marker = folium.Marker(
            location=coords,
            tooltip=name,
            popup=folium.Popup(popup_html, max_width=260),
            icon=icon
        )
        if p["type"] == "positive":
            marker.add_to(cluster_pos)
        else:
            marker.add_to(cluster_neg)

    legend_html = """
    <div style="
     position: fixed; bottom: 20px; left: 20px; z-index: 9999;
     background: white; padding: 10px 12px; border: 1px solid #ccc; border-radius: 8px;
     font-size: 12px; line-height: 1.3;">
     <b>Legend</b><br>
     <span style="color:green;">●</span> Positive categories<br>
     <span style="color:red;">●</span> Negative categories<br>
     Icons vary by category
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    MiniMap(toggle_display=True).add_to(m)
    Fullscreen().add_to(m)
    folium.LayerControl(position="topright").add_to(m)

    map_html = m._repr_html_()

    positive_pois = [p for p in filtered if p["type"] == "positive"]
    negative_pois = [p for p in filtered if p["type"] == "negative"]

    summary_payload = {
        "property_type": property_type,
        "location": location,
        "radius_miles": radius_miles,
        "positive_pois": positive_pois,
        "negative_pois": negative_pois,
    }

    summary_response = model.generate_content(
        """
        You are helping evaluate locations for property acquisition.

        Given the JSON below, identify:
        1) The most important POSITIVE points of interest for this property type.
        2) The most important NEGATIVE points of interest or risks.
        3) A short, practical summary (3–5 sentences) of how attractive this location is.

        Focus on the relevance of each POI to the property type and its distance.

        Return a concise, human-readable explanation, not JSON.
        """ + "\n\nJSON:\n" + json.dumps(summary_payload, indent=2)
    )

    summary_text = summary_response.text

    st.subheader("Parsed input")
    st.write(f"**Property type:** {property_type}")
    st.write(f"**Location:** {location}")
    st.write(f"**Radius:** {radius_miles} miles")

    st.subheader("Map")
    st_html(map_html, height=600)

    st.subheader("Gemini summary")
    st.write(summary_text)
