import streamlit as st
import osmnx as ox
import networkx as nx
import pandas as pd
import folium
from streamlit_folium import st_folium
import xml.etree.ElementTree as ET
from io import BytesIO
import json
from PIL import Image
import streamlit.components.v1 as components

# -----------------------------
# Setup Streamlit Page
# -----------------------------
st.set_page_config(page_title="🏃 Running Loop Generator", layout="centered")

# Centered Logo
logo = Image.open("logo Myloop.webp")
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image(logo, width=200)

st.title("🏃‍♂️ Running Loop Route Generator")
st.markdown("👟 **We try to detect your location! Otherwise click manually.**")

# -----------------------------
# Detect Location
# -----------------------------
st.session_state.setdefault("location_detected", False)
st.session_state.setdefault("map_center", [24.7136, 46.6753])  # Default Riyadh
st.session_state.setdefault("map_zoom", 13)

# Try to read location from URL query params
location_param = st.query_params.get("location_data")

if location_param and not st.session_state["location_detected"]:
    try:
        location = json.loads(location_param[0])
        lat = location["lat"]
        lon = location["lon"]
        st.session_state.map_center = [lat, lon]
        st.session_state.map_zoom = 15
        st.session_state.location_detected = True
        st.success("📍 Location detected successfully!")
    except Exception as e:
        st.warning("📍 Could not detect location, defaulting to Riyadh.")

# Inject JS code to get user's location and update URL
components.html(
    """
    <script>
    if (!window.location.search.includes("location_data")) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const latitude = position.coords.latitude;
                const longitude = position.coords.longitude;
                const data = {lat: latitude, lon: longitude};
                const queryString = new URLSearchParams({location_data: JSON.stringify(data)}).toString();
                window.location.search = '?' + queryString;
            },
            (error) => {
                const queryString = new URLSearchParams({location_data: "null"}).toString();
                window.location.search = '?' + queryString;
            }
        );
    }
    </script>
    """,
    height=0
)

# -----------------------------
# Initialize Map
# -----------------------------
m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)

if "latlon" not in st.session_state:
    st.session_state.latlon = None
if "route_df" not in st.session_state:
    st.session_state.route_df = None

if st.session_state.latlon:
    folium.Marker(
        location=st.session_state.latlon,
        popup="📍 Start Point",
        icon=folium.Icon(color="green", icon="map-marker")
    ).add_to(m)

if st.session_state.route_df is not None:
    folium.PolyLine(
        locations=st.session_state.route_df[["lat", "lon"]].values.tolist(),
        color="blue",
        weight=5
    ).add_to(m)

click_result = st_folium(m, height=500, returned_objects=["last_clicked"], key="main-map")

if click_result and click_result.get("last_clicked"):
    lat = click_result["last_clicked"]["lat"]
    lon = click_result["last_clicked"]["lng"]
    st.session_state.latlon = (lat, lon)

# -----------------------------
# Generate Simple Running Loop
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

# -----------------------------
# Export GPX
# -----------------------------
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
# Generate Route and Show Download
# -----------------------------
if st.session_state.latlon:
    lat, lon = st.session_state.latlon
    st.success(f"📍 Selected Point: ({lat:.5f}, {lon:.5f})")

    distance_km = st.slider("🎯 Choose Loop Distance (km)", 1.0, 15.0, 5.0, 0.5)

    if st.button("🚀 Generate Running Loop"):
        try:
            G, route, actual_distance_km = generate_simple_loop(lat, lon, distance_km)
            coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]
            route_df = pd.DataFrame(coords, columns=["lat", "lon"])
            st.session_state.route_df = route_df

            st.success(f"✅ Generated loop: {actual_distance_km:.2f} km")
        except Exception as e:
            st.error(f"❌ Error: {e}")

# -----------------------------
# Download GPX + Komoot Upload
# -----------------------------
if st.session_state.route_df is not None:
    gpx_data = export_gpx(st.session_state.route_df)
    st.download_button(
        label="📥 Download GPX",
        data=gpx_data,
        file_name="running_loop.gpx",
        mime="application/gpx+xml"
    )

    if st.button("📲 Upload GPX to Komoot"):
        js = "window.open('https://www.komoot.com/upload')"
        components.html(f"<script>{js}</script>", height=0)
