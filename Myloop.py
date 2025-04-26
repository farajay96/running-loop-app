import streamlit as st
import osmnx as ox
import networkx as nx
import pandas as pd
import folium
from streamlit_folium import st_folium
import xml.etree.ElementTree as ET
from io import BytesIO
import streamlit.components.v1 as components
from PIL import Image

# -----------------------------
# Setup Streamlit Page
# -----------------------------
st.set_page_config(page_title="🏃 Running Loop Generator", layout="centered")

# Centered Logo
logo = Image.open("logo Myloop.webp")  # Make sure this is the new WEBP logo
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image(logo, width=200)

st.title("🏃‍♂️ Running Loop Route Generator")
st.markdown("👟 **Select a neighborhood, click a start point, and create your running loop!**")

# -----------------------------
# Simple Fast Loop Generator
# -----------------------------
def generate_simple_loop(start_lat, start_lon, distance_km):
    segment_km = distance_km / 4

    # Compute rough points
    east = (start_lat, start_lon + segment_km / 111)
    north = (start_lat + segment_km / 111, east[1])
    west = (north[0], start_lon)

    # Load a small road network
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
            route.extend(path[:-1])  # avoid duplicate nodes
            total_length += nx.path_weight(G, path, weight='length')
        except Exception as e:
            raise RuntimeError(f"Path error: {e}")

    route.append(start_node)
    return G, route, total_length / 1000  # distance in km

# -----------------------------
# GPX Exporter
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
# Session State Setup
# -----------------------------
if "latlon" not in st.session_state:
    st.session_state.latlon = None
if "route_df" not in st.session_state:
    st.session_state.route_df = None
if "map_center" not in st.session_state:
    st.session_state.map_center = [24.7136, 46.6753]
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 12

# -----------------------------
# Neighborhoods
# -----------------------------
neighborhoods = {
    "Al Ghadir": (24.7915, 46.6548),
    "Al Wadi (الوادي)": (24.7906, 46.6507),
    "Al Yasmin": (24.8240, 46.6357),
    "Al Nakheel": (24.7528, 46.6567),
    "Al Malaz": (24.6648, 46.7318),
    "Al Malqa": (24.7795, 46.6182),
    "Al Mughrizat": (24.7483, 46.7410),
    "Al Murabba": (24.6425, 46.7134),
    "Al Muruj": (24.7326, 46.6641),
    "Al Rawdah": (24.7403, 46.7605),
    "Al Rehab": (24.6789, 46.7102),
    "Al Sulaymaniyah": (24.7075, 46.6861),
    "Al Nuzha": (24.7687, 46.6987),
    "Diplomatic Quarter (DQ)": (24.6662, 46.6169),
    "King Abdullah District": (24.7292, 46.7129),
    "King Saud University": (24.7247, 46.6278),
    "Olaya": (24.6928, 46.6857),
    "Al Muhammadiyah": (24.7333, 46.6437)
}

selected_neighborhood = st.selectbox(
    "🏙️ Select Neighborhood",
    options=list(neighborhoods.keys())
)

if selected_neighborhood:
    center_lat, center_lon = neighborhoods[selected_neighborhood]
    st.session_state.map_center = [center_lat, center_lon]
    st.session_state.map_zoom = 15

# -----------------------------
# Build Map
# -----------------------------
m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)

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
# Generate Route
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
# Download GPX + Upload to Komoot
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
