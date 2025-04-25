import streamlit as st
import osmnx as ox
import networkx as nx
import pandas as pd
import pydeck as pdk
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
st.markdown("Click on the map to select your start location in **Riyadh**, set your desired distance, and generate a looped running route.")

# Map centered on Riyadh
default_lat, default_lon = 24.7136, 46.6753
m = folium.Map(location=[default_lat, default_lon], zoom_start=13)
click_result = st_folium(m, height=450, returned_objects=["last_clicked"])

if click_result and click_result.get("last_clicked"):
    lat = click_result["last_clicked"]["lat"]
    lon = click_result["last_clicked"]["lng"]
    st.success(f"📍 Selected location: ({lat:.5f}, {lon:.5f})")

    distance_km = st.slider("Select loop distance (km)", 1.0, 15.0, 5.0, 0.5)

    if st.button("Generate Route"):
        try:
            G, route, actual_km = generate_loop_route(lat, lon, distance_km)
            coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]
            route_df = pd.DataFrame(coords, columns=["lat", "lon"])

            path = [[row["lon"], row["lat"]] for _, row in route_df.iterrows()]
            path_df = pd.DataFrame([{"path": path}])

            route_layer = pdk.Layer(
                "PathLayer",
                data=path_df,
                get_path="path",
                get_width=5,
                get_color=[0, 100, 255],
                width_min_pixels=2
            )

            point_layer = pdk.Layer(
                "ScatterplotLayer",
                data=pd.DataFrame([route_df.iloc[0]]),
                get_position=["lon", "lat"],
                get_color=[0, 255, 0],
                get_radius=30,
            )

            view_state = pdk.ViewState(
                latitude=route_df["lat"].mean(),
                longitude=route_df["lon"].mean(),
                zoom=15,
                pitch=0
            )

            st.pydeck_chart(pdk.Deck(initial_view_state=view_state, layers=[route_layer, point_layer]))
            st.success(f"✅ Route generated: {actual_km:.2f} km")

            gpx_data = export_gpx(route_df)
            st.download_button(
                label="📥 Download GPX",
                data=gpx_data,
                file_name="running_loop.gpx",
                mime="application/gpx+xml"
            )

        except Exception as e:
            st.error(f"❌ Error: {e}")
else:
    st.warning("👆 Click on the map to select your start location.")
