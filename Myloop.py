import streamlit as st
import osmnx as ox
import networkx as nx
import pandas as pd
import folium
from streamlit_folium import st_folium
import xml.etree.ElementTree as ET
from io import BytesIO

# -----------------------------
# Route Generator
# -----------------------------
def generate_loop_route(start_lat, start_lon, distance_km):
    segment_distance_km = distance_km / 4
    east_point = (start_lat, start_lon + segment_distance_km / 111)
    north_point = (start_lat + segment_distance_km / 111, east_point[1])
    west_point = (north_point[0], start_lon)

    G = ox.graph_from_point((start_lat, start_lon), dist=distance_km * 700, network_type='walk', simplify=True)
    start_node = ox.distance.nearest_nodes(G, X=start_lon, Y=start_lat)
    east_node = ox.distance.nearest_nodes(G, X=east_point[1], Y=east_point[0])
    north_node = ox.distance.nearest_nodes(G, X=north_point[1], Y=north_point[0])
    west_node = ox.distance.nearest_nodes(G, X=west_point[1], Y=west_point[0])

    nodes_sequence = [start_node, east_node, north_node, west_node, start_node]
    loop_route, used_edges, total_distance_m = [], set(), 0

    for i in range(len(nodes_sequence) - 1):
        u, v = nodes_sequence[i], nodes_sequence[i + 1]
        path = nx.shortest_path(G, u, v, weight='length')
        segment_edges = {(path[j], path[j + 1]) for j in range(len(path) - 1)}
        if used_edges.intersection(segment_edges):
            raise RuntimeError("This segment reuses roads. Try increasing distance or changing location.")
        loop_route.extend(path[:-1])
        used_edges.update(segment_edges)
        total_distance_m += nx.path_weight(G, path, weight='length')

    loop_route.append(start_node)
    return G, loop_route, total_distance_m / 1000

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
st.set_page_config(page_title="🏃 Riyadh Loop Generator", layout="centered")
st.title("🏃‍♂️ Running Loop Route Generator")
st.markdown("Click on the map to select your start location in **Riyadh**, then choose a loop distance.")

# -----------------------------
# Session state defaults
# -----------------------------
if "latlon" not in st.session_state:
    st.session_state.latlon = None
if "route_df" not in st.session_state:
    st.session_state.route_df = None
if "actual_km" not in st.session_state:
    st.session_state.actual_km = None
if "map_center" not in st.session_state:
    st.session_state.map_center = [24.7136, 46.6753]  # Riyadh
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 13

# -----------------------------
# Map Construction
# -----------------------------
m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)

# Draw marker if clicked before
if st.session_state.latlon:
    folium.Marker(
        location=st.session_state.latlon,
        popup="📍 Start Point",
        icon=folium.Icon(color="green", icon="map-marker")
    ).add_to(m)

# Draw route if exists
if st.session_state.route_df is not None:
    folium.PolyLine(
        locations=st.session_state.route_df[["lat", "lon"]].values.tolist(),
        color="blue",
        weight=5,
        popup="Loop Route"
    ).add_to(m)

# Show the interactive map
click_result = st_folium(m, height=500, returned_objects=["last_clicked", "map_bounds"], key="main-map")

# -----------------------------
# Process map interaction
# -----------------------------
# Update map center and zoom based on user interaction
if click_result and click_result.get("map_bounds"):
    bounds = click_result["map_bounds"]
    center_lat = (bounds["_northEast"]["lat"] + bounds["_southWest"]["lat"]) / 2
    center_lon = (bounds["_northEast"]["lng"] + bounds["_southWest"]["lng"]) / 2
    st.session_state.map_center = [center_lat, center_lon]

    lat_span = abs(bounds["_northEast"]["lat"] - bounds["_southWest"]["lat"])
    if lat_span < 0.005:
        st.session_state.map_zoom = 17
    elif lat_span < 0.01:
        st.session_state.map_zoom = 16
    elif lat_span < 0.02:
        st.session_state.map_zoom = 15
    else:
        st.session_state.map_zoom = 13

# Update selected point if clicked
if click_result and click_result.get("last_clicked"):
    lat = click_result["last_clicked"]["lat"]
    lon = click_result["last_clicked"]["lng"]
    st.session_state.latlon = (lat, lon)

# -----------------------------
# UI Logic
# -----------------------------
if st.session_state.latlon:
    lat, lon = st.session_state.latlon
    st.success(f"📍 Start: ({lat:.5f}, {lon:.5f})")

    distance_km = st.slider("Select loop distance (km)", 1.0, 15.0, 5.0, 0.5)

    if st.button("🚀 Generate Route"):
        try:
            G, route, actual_km = generate_loop_route(lat, lon, distance_km)
            coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]
            route_df = pd.DataFrame(coords, columns=["lat", "lon"])
            st.session_state.route_df = route_df
            st.session_state.actual_km = actual_km
        except Exception as e:
            st.error(f"❌ Error generating route: {e}")

if st.session_state.route_df is not None:
    st.success(f"✅ Route: {st.session_state.actual_km:.2f} km")
    gpx_data = export_gpx(st.session_state.route_df)
    st.download_button(
        label="📥 Download GPX",
        data=gpx_data,
        file_name="running_loop.gpx",
        mime="application/gpx+xml"
    )
