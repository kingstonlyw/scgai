This is the folder for those working with the Acquisitions team.

Using demo.ipynb:
- Download pdf files you want analyzed locally and move them to the same file as demo.ipynb
- Edit user_input variable in the first code block
- Run code blocks sequentially. Several files will be created, such as data_file.txt, responses.txt, and table.csv

Using starwood_project_map.py

- Finds nearby POIs around an address and radius using OSMnx (change address and radius in the code block)
- Computes distances with geopy and writes to "poi_analysis.json".
- Shows only the closest POI per category on an interactive Folium map "poi_map.html".

To run use

pip install osmnx geopy folium
python starwood_project_map.py
