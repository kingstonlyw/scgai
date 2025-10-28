import osmnx as ox
import json
from geopy.distance import geodesic
import matplotlib.pyplot as plt

# API call here to get chat to be able to convert a natural language input into location and radius of search.
location = "3413 Strand Ct, Ann Arbor, MI"
radius_miles = 1
miles_to_meters = 1609.34
radius_meters = radius_miles * miles_to_meters

lat, lon = ox.geocode(location)

tag_map = {
    "park": {"leisure": "park"},
    "school": {"amenity": "school"},
    "transit_station": {"public_transport": "station"},
    "university": {"amenity": "university"},
    "hospital": {"amenity": "hospital"},
    "industrial": {"landuse": "industrial"},
    "landfill": {"landuse": "landfill"},
    "highway": {"highway": True}
}

positive_categories = ["park", "school", "transit_station", "university", "hospital"]
negative_categories = ["industrial", "landfill", "highway"]

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

            # Drop rows with NaN geometries
            gdf = gdf.dropna(subset=["geometry"])

            for _, row in gdf.iterrows():
                geom = row.geometry
                if geom.is_empty:
                    continue

                try:
                    centroid = geom.centroid
                    if centroid.is_empty or centroid.x != centroid.x or centroid.y != centroid.y:
                        continue  # skip if NaN
                    coords = (centroid.y, centroid.x)
                except Exception:
                    continue

                if coords[0] != coords[0] or coords[1] != coords[1]:  # skip if NaN
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
        except Exception as e:
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

# -------- Plot 10 closest points overall --------
top10_overall = sorted(_all_positive, key=lambda x: x["distance_miles"])[:10]

if top10_overall:
    poi_lats = [p["coordinates"][0] for p in top10_overall]
    poi_lons = [p["coordinates"][1] for p in top10_overall]
    poi_labels = [p["name"] if p["name"] else p["category"] for p in top10_overall]
    poi_colors = ["tab:green" if p["type"] == "positive" else "tab:red" for p in top10_overall]

    plt.figure(figsize=(7, 7))
    plt.scatter([lon], [lat], s=100, marker="*", label="Center", zorder=3)
    plt.scatter(poi_lons, poi_lats, s=50, c=poi_colors, zorder=2)

    for x, y, lbl in zip(poi_lons, poi_lats, poi_labels):
        plt.annotate(lbl, (x, y), xytext=(3, 3), textcoords="offset points", fontsize=8)

    plt.title(f"Top 10 Closest POIs within {radius_miles} mile(s)\n{location}")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.legend(loc="best")
    plt.gca().set_aspect('equal', adjustable='box')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("poi_plot.png", dpi=200)
    plt.close()
    print("Saved plot to poi_plot.png")
else:
    print("No POIs found to plot.")
