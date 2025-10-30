import osmnx as ox
import json
from geopy.distance import geodesic
import folium

# Input
location = "3413 Strand Ct, Ann Arbor, MI"
radius_miles = 1
miles_to_meters = 1609.34
radius_meters = radius_miles * miles_to_meters

lat, lon = ox.geocode(location)

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
    "highway": {"highway": True},
    "waste_disposal": {"amenity": "waste_disposal"},
    "quarry": {"landuse": "quarry"},
    "power_station": {"power": "plant"},
    "noise_barrier": {"barrier": "noise_barrier"}
}


positive_categories = [
    "park", "school", "university", "hospital", "clinic", "transit_station",
    "bus_stop", "supermarket", "pharmacy", "library", "restaurant", "cafe",
    "bank", "playground", "sports_centre", "place_of_worship"
]

negative_categories = [
    "industrial", "construction", "landfill", "highway", "waste_disposal",
    "quarry", "power_station", "noise_barrier"
]


positive_places = []
negative_places = []

for category_list, label, storage in [
    (positive_categories, "positive", positive_places),
    (negative_categories, "negative", negative_places),
]:
    for category in category_list:
        try:
            gdf = ox.features_from_point((lat, lon), tags=tag_map[category], dist=radius_meters)
            if gdf.empty:
                continue

            gdf = gdf.dropna(subset=["geometry"])

            for _, row in gdf.iterrows():
                geom = row.geometry
                if geom.is_empty:
                    continue

                try:
                    centroid = geom.centroid
                    if centroid.is_empty or centroid.x != centroid.x or centroid.y != centroid.y:
                        continue
                    coords = (centroid.y, centroid.x)
                except Exception:
                    continue

                if coords[0] != coords[0] or coords[1] != coords[1]:
                    continue

                place_name = row.get("name", category)
                dist_miles = round(geodesic((lat, lon), coords).miles, 2)
                if not isinstance(dist_miles, float) or dist_miles != dist_miles:
                    continue

                storage.append({
                    "name": place_name,
                    "type": label,
                    "category": category,
                    "distance_miles": dist_miles,
                    "coordinates": [coords[0], coords[1]]
                })
        except Exception:
            print(f"Nothing for {category}")

num_positive = 10
num_negative = 3

_all_positive = list(positive_places)
_all_negative = list(negative_places)

positive_places = sorted(positive_places, key=lambda x: x["distance_miles"])[:num_positive]
negative_places = sorted(negative_places, key=lambda x: x["distance_miles"])[:num_negative]

poi_data = {
    "location": location,
    "radius in miles": radius_miles,
    "POIs": positive_places + negative_places
}

with open("poi_analysis.json", "w") as f:
    json.dump(poi_data, f, indent=4)

print(f"Found {len(positive_places)} positive and {len(negative_places)} negative places.")

m = folium.Map(location=[lat, lon], zoom_start=15, control_scale=True)

folium.Circle(
    location=[lat, lon],
    radius=radius_meters,
    fill=False,
    color="#2563eb",
    weight=2,
    opacity=0.7,
).add_to(m)

folium.Marker(
    [lat, lon],
    icon=folium.Icon(color="blue", icon="star"),
    tooltip="Center",
    popup=f"{location}\nRadius: {radius_miles} miles",
).add_to(m)

def closest_by_category(pois):
    best = {}
    for p in pois:
        c = p["category"]
        if c not in best or p["distance_miles"] < best[c]["distance_miles"]:
            best[c] = p
    return best

closest_positive = closest_by_category(_all_positive)
closest_negative = closest_by_category(_all_negative)

fg_pos = folium.FeatureGroup(name="Closest Positive (one per category)", show=True)
fg_neg = folium.FeatureGroup(name="Closest Negative (one per category)", show=True)

for cat, p in sorted(closest_positive.items()):
    folium.CircleMarker(
        location=p["coordinates"],
        radius=8,
        color="green",
        fill=True,
        fill_opacity=0.9,
        popup=folium.Popup(
            f"<b>{p['name']}</b><br>Category: {cat}<br>Distance: {p['distance_miles']} mi",
            max_width=260,
        ),
        tooltip=f"{cat} • {p['name'] or cat}",
    ).add_to(fg_pos)

for cat, p in sorted(closest_negative.items()):
    folium.CircleMarker(
        location=p["coordinates"],
        radius=8,
        color="red",
        fill=True,
        fill_opacity=0.9,
        popup=folium.Popup(
            f"<b>{p['name']}</b><br>Category: {cat}<br>Distance: {p['distance_miles']} mi",
            max_width=260,
        ),
        tooltip=f"{cat} • {p['name'] or cat}",
    ).add_to(fg_neg)

fg_pos.add_to(m)
fg_neg.add_to(m)
folium.LayerControl(position="topright").add_to(m)

m.save("poi_map.html")
print("Saved interactive map to poi_map.html")
