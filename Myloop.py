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
logo = Image.open("logo Myloop.webp")  # Make sure the logo file exists
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image(logo, width=200)

st.title("🏃‍♂️ Running Loop Route Generator")
st.markdown("👟 **Allow location or click manually to select your start point!**")

# -----------------------------
# Utility Functions
# -----------------------------
@st.cache_data(show_spinner=False)
def reverse_geocode(lat, lon):
    geolocator = Nominatim(user_agent="myloop-app")
    location = geolocator.reverse((lat, lon), language='en')
    if location and location.address:
        return location.address
    return None

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
    return G, route, total_length / 1000  # in kilometers

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
    st.session_state.map_center = [24.7136, 46.6753]  # Default Riyadh
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 12

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

click_result = st_folium(m, height=500, returned_objects=["last_clicked", "center"], key="main-map")

# -----------------------------
# Handle Map Interactions
# -----------------------------
if click_result:
    if click_result.get("center") and not st.session_state.latlon:
        center = click_result["center"]
        st.session_state.map_center = [center["lat"], center["lng"]]
        st.session_state.map_zoom = 15
        detected_location = reverse_geocode(center["lat"], center["lng"])
        if detected_location:
            st.info(f"📍 Detected Location: {detected_location}")
    if click_result.get("last_clicked"):
        lat = click_result["last_clicked"]["lat"]
        lon = click_result["last_clicked"]["lng"]
        st.session_state.latlon = (lat, lon)

# -----------------------------
# Generate Running Loop
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
# Download GPX 
# -----------------------------
if st.session_state.route_df is not None:
    gpx_data = export_gpx(st.session_state.route_df)
    st.download_button(
        label="📥 Download GPX",
        data=gpx_data,
        file_name="running_loop.gpx",
        mime="application/gpx+xml"
    )
