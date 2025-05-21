import streamlit as st
import osmnx as ox
import networkx as nx
import pandas as pd
import folium
from streamlit_folium import st_folium
import xml.etree.ElementTree as ET
from io import BytesIO
from PIL import Image
from streamlit_geolocation import streamlit_geolocation

# -----------------------------
# Setup Streamlit Page
# -----------------------------
st.set_page_config(page_title="🏃 Running Loop Generator", layout="centered")

# Load Logo
logo = Image.open("logo Myloop.webp")
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image(logo, width=200)

st.title(":running: Running Loop Route Generator")

# -----------------------------
# Route Generation Functions
# -----------------------------
def generate_simple_loop(start_lat, start_lon, distance_km):
    segment_km = distance_km / 4
    east = (start_lat, start_lon + segment_km / 111)
    north = (start_lat + segment_km / 111, east[1])
    west = (north[0], start_lon)

    G = ox.graph_from_point((start_lat, start_lon), dist=distance_km * 600, network_type='walk', simplify=True)

    start_node = ox.distance.nearest_nodes(G, start_lon, start_lat)
    east_node = ox.distance.nearest_nodes(G, east[1], east[0])
    north_node = ox.distance.nearest_nodes(G, north[1], north[0])
    west_node = ox.distance.nearest_nodes(G, west[1], west[0])

    nodes_sequence = [start_node, east_node, north_node, west_node, start_node]

    route = []
    total_length = 0
    for i in range(len(nodes_sequence) - 1):
        try:
            path = nx.shortest_path(G, nodes_sequence[i], nodes_sequence[i + 1], weight='length')
            route.extend(path[:-1])
            total_length += nx.path_weight(G, path, weight='length')
        except Exception as e:
            raise RuntimeError(f"Path error: {e}")

    route.append(start_node)
    return G, route, total_length / 1000

def find_best_loop(lat, lon, target_km, tolerance=0.15, max_attempts=10):
    for i in range(max_attempts):
        scale = 1 - (0.04 * i)
        try_km = target_km * scale
        try:
            G, route, actual_km = generate_simple_loop(lat, lon, try_km)
            if abs(actual_km - target_km) <= tolerance:
                return G, route, actual_km
        except Exception:
            continue
    return G, route, actual_km

def export_gpx(route_df):
    gpx = ET.Element("gpx", version="1.1", creator="MyLoopApp")
    trk = ET.SubElement(gpx, "trk")
    trkseg = ET.SubElement(trk, "trkseg")
    for _, row in route_df.iterrows():
        trkpt = ET.SubElement(trkseg, "trkpt", lat=str(row["lat"]), lon=str(row["lon"]))
        ET.SubElement(trkpt, "ele").text = "0"
    tree = ET.ElementTree(gpx)
    gpx_bytes = BytesIO()
    tree.write(gpx_bytes, encoding="utf-8", xml_declaration=True)
    return gpx_bytes.getvalue()

# -----------------------------
# Step 1: Detect Location
# -----------------------------
st.subheader("Step 1: Detect Your Location")
location = streamlit_geolocation()

if location['latitude'] is not None:
    st.session_state.map_center = [location["latitude"], location["longitude"]]
    st.session_state.map_zoom = 15
    st.session_state.location_detected = True
    st.success("Location detected. Scroll down to select a start point or use your current one.")
else:
    st.session_state.map_center = [24.7136, 46.6753]  # Riyadh fallback
    st.session_state.map_zoom = 13
    st.warning("Couldn't detect location automatically. You can click on the map to select a start point.")

# -----------------------------
# Step 2: Select Start Point
# -----------------------------
st.subheader("Step 2: Select a Starting Point")

if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 13
if "latlon" not in st.session_state:
    st.session_state.latlon = None
if "route_df" not in st.session_state:
    st.session_state.route_df = None

m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)

if st.session_state.get("location_detected"):
    folium.CircleMarker(
        location=st.session_state.map_center,
        radius=7,
        color="blue",
        fill=True,
        fill_color="blue",
        fill_opacity=0.8,
        popup="You are here"
    ).add_to(m)

if st.session_state.latlon:
    folium.Marker(
        location=st.session_state.latlon,
        popup="Start Point",
        icon=folium.Icon(color="green", icon="map-marker")
    ).add_to(m)

if st.session_state.route_df is not None:
    folium.PolyLine(
        locations=st.session_state.route_df[["lat", "lon"]].values.tolist(),
        color="blue",
        weight=5
    ).add_to(m)

    mid_idx = len(st.session_state.route_df) // 2
    mid_point = st.session_state.route_df.iloc[mid_idx]
    offset_lat = mid_point["lat"] + 0.0005
    offset_lon = mid_point["lon"] + 0.0005

    folium.Marker(
        location=[offset_lat, offset_lon],
        popup=f"Distance: {st.session_state.generated_km:.2f} km",
        icon=folium.DivIcon(html=f"""
            <div style='font-size: 14pt; color: black; background-color: white; padding: 2px; border-radius: 5px;'>
                {st.session_state.generated_km:.2f} km
            </div>
        """)
    ).add_to(m)

click_result = st_folium(m, height=500, returned_objects=["last_clicked"], key="main-map")

if click_result and click_result.get("last_clicked"):
    lat = click_result["last_clicked"]["lat"]
    lon = click_result["last_clicked"]["lng"]
    st.session_state.latlon = (lat, lon)

if st.session_state.latlon is None and st.session_state.get("location_detected"):
    st.session_state.latlon = tuple(st.session_state.map_center)

# -----------------------------
# Step 3: Choose Distance and Generate Route
# -----------------------------
if st.session_state.latlon:
    st.subheader("Step 3: Choose Loop Distance")
    lat, lon = st.session_state.latlon
    distance_km = st.slider("Choose Loop Distance (km)", 1.0, 15.0, 5.0, 0.5)

    if st.button("Generate Running Loop"):
        try:
            G, route, actual_distance_km = find_best_loop(lat, lon, distance_km)
            coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]
            route_df = pd.DataFrame(coords, columns=["lat", "lon"])
            st.session_state.route_df = route_df
            st.session_state.generated_km = actual_distance_km
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

# -----------------------------
# Step 4: Download + Komoot Instructions
# -----------------------------
if st.session_state.route_df is not None:
    gpx_data = export_gpx(st.session_state.route_df)
    file_name = "running_loop.gpx"

    st.subheader("Step 4: Download and Use in Komoot")
    download_clicked = st.download_button(
        label="Download GPX File",
        data=gpx_data,
        file_name=file_name,
        mime="application/gpx+xml"
    )

    if download_clicked:
        st.markdown("---")
        st.info(
            f"""
            Your route was saved as **`{file_name}`** in your **Downloads** folder.

            To use it in Komoot:
            1. Open [komoot.com/upload](https://www.komoot.com/upload)
            2. Upload the file manually.

            On mobile:
            - Open the **Komoot app**
            - Go to **Profile → Routes → Import**
            - Select the file from your **Files** or **Downloads** folder.
            """
        )
        st.markdown("---")
