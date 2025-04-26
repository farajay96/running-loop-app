import streamlit as st
import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import xml.etree.ElementTree as ET
from io import BytesIO
import streamlit.components.v1 as components

# -----------------------------
# Smoothness Scoring
# -----------------------------
def calculate_loop_smoothness(G, loop):
    angles = []
    coords = [(G.nodes[n]['x'], G.nodes[n]['y']) for n in loop]

    for i in range(1, len(coords) - 1):
        a = np.array(coords[i - 1])
        b = np.array(coords[i])
        c = np.array(coords[i + 1])

        ba = a - b
        bc = c - b

        cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
        angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))
        angles.append(np.degrees(angle))

    total_angle_change = np.sum(np.abs(angles))
    return total_angle_change

# -----------------------------
# Smart Loop Generator
# -----------------------------
def generate_smart_loops(G, start_node, desired_distance_km, tolerance=0.10, max_cycles=500):
    cycles = list(nx.simple_cycles(G.to_directed()))
    loops = []

    desired_distance_m = desired_distance_km * 1000
    min_distance_m = desired_distance_m * (1 - tolerance)
    max_distance_m = desired_distance_m * (1 + tolerance)

    for cycle in cycles[:max_cycles]:
        cycle.append(cycle[0])
        try:
            length = sum(
                G.edges[cycle[i], cycle[i + 1], 0]['length']
                for i in range(len(cycle) - 1)
            )
            if min_distance_m <= length <= max_distance_m:
                smoothness = calculate_loop_smoothness(G, cycle)
                loops.append((cycle, length, smoothness))
        except Exception:
            continue

    # Sort by smoothness (lower = better)
    loops.sort(key=lambda x: x[2])
    return loops

# -----------------------------
# GPX Exporter
# -----------------------------
def export_gpx(route_df):
    gpx = ET.Element("gpx", version="1.1", creator="RunningLoopApp")
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
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="🏃 Running Loop Generator", layout="centered")
st.title("🏃‍♂️ Running Loop Route Generator")
st.markdown("👟 **Select a neighborhood to zoom in, then click on the map to pick your starting point.**")

# -----------------------------
# Session State Setup
# -----------------------------
if "latlon" not in st.session_state:
    st.session_state.latlon = None
if "route_df" not in st.session_state:
    st.session_state.route_df = None
if "loops_found" not in st.session_state:
    st.session_state.loops_found = []
if "map_center" not in st.session_state:
    st.session_state.map_center = [24.7136, 46.6753]  # Riyadh center
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

# Update map center immediately
if selected_neighborhood:
    center_lat, center_lon = neighborhoods[selected_neighborhood]
    st.session_state.map_center = [center_lat, center_lon]
    st.session_state.map_zoom = 15

# -----------------------------
# Build Map
# -----------------------------
m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)

# Add marker if selected
if st.session_state.latlon:
    folium.Marker(
        location=st.session_state.latlon,
        popup="📍 Start Point",
        icon=folium.Icon(color="green", icon="map-marker")
    ).add_to(m)

# Add route if exists
if st.session_state.route_df is not None:
    folium.PolyLine(
        locations=st.session_state.route_df[["lat", "lon"]].values.tolist(),
        color="blue",
        weight=5,
        popup="Loop Route"
    ).add_to(m)

click_result = st_folium(m, height=500, returned_objects=["last_clicked"], key="main-map")

if click_result and click_result.get("last_clicked"):
    lat = click_result["last_clicked"]["lat"]
    lon = click_result["last_clicked"]["lng"]
    st.session_state.latlon = (lat, lon)

# -----------------------------
# Generate Loops
# -----------------------------
if st.session_state.latlon:
    lat, lon = st.session_state.latlon
    st.success(f"📍 Selected Point: ({lat:.5f}, {lon:.5f})")

    distance_km = st.slider("🎯 Choose Loop Distance (km)", 1.0, 15.0, 5.0, 0.5)

    if st.button("🚀 Find Loops"):
        try:
            G = ox.graph_from_point((lat, lon), dist=distance_km * 800, network_type='walk', simplify=True)
            start_node = ox.distance.nearest_nodes(G, lon, lat)

            loops = generate_smart_loops(G, start_node, distance_km, tolerance=0.10, max_cycles=800)
            st.session_state.loops_found = loops

            if not loops:
                st.error("❌ No loop found matching the requested distance. Try selecting a different area.")
            else:
                st.success(f"✅ Found {len(loops)} possible loops! (Sorted by smoothness)")

        except Exception as e:
            st.error(f"❌ Error: {e}")

# -----------------------------
# Let user pick and download loop
# -----------------------------
if st.session_state.loops_found:
    loop_options = [f"Loop {i+1}: {length/1000:.2f} km (Smoothness: {smoothness:.1f})" for i, (loop, length, smoothness) in enumerate(st.session_state.loops_found)]
    selected_loop_idx = st.selectbox("🛣️ Select a loop to display and download:", options=list(range(len(loop_options))), format_func=lambda x: loop_options[x])

    selected_loop, selected_length, selected_smoothness = st.session_state.loops_found[selected_loop_idx]
    st.success(f"✅ Selected Loop Distance: {selected_length/1000:.2f} km | Smoothness Score: {selected_smoothness:.1f}")

    # Build route_df
    selected_latlons = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in selected_loop]
    route_df = pd.DataFrame(selected_latlons, columns=["lat", "lon"])
    st.session_state.route_df = route_df

    # Draw the selected loop
    m2 = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)
    folium.PolyLine(locations=route_df[["lat", "lon"]].values.tolist(), color="blue", weight=5).add_to(m2)
    st_folium(m2, height=500, key="selected-loop-map")

    # Download GPX
    gpx_data = export_gpx(route_df)
    st.download_button(
        label="📥 Download GPX",
        data=gpx_data,
        file_name="running_loop.gpx",
        mime="application/gpx+xml"
    )

    # Komoot Upload Button
    if st.button("📲 Upload GPX to Komoot"):
        js = "window.open('https://www.komoot.com/upload')"
        components.html(f"<script>{js}</script>", height=0)
