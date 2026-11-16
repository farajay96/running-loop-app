
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
st.set_page_config(
    page_title="🏃 Running Loop Generator",
    layout="centered"
)

# Initialize session state
if "map_center" not in st.session_state:
    st.session_state.map_center = [24.7136, 46.6753]

if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 13

if "latlon" not in st.session_state:
    st.session_state.latlon = None

if "route_df" not in st.session_state:
    st.session_state.route_df = None

if "location_detected" not in st.session_state:
    st.session_state.location_detected = False

# -----------------------------
# Load Logo
# -----------------------------
try:
    logo = Image.open("logo Myloop.webp")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(logo, width=200)
except Exception:
    pass

st.title(":running: Running Loop Route Generator")

# -----------------------------
# Route Generation Functions
# -----------------------------
def generate_simple_loop(start_lat, start_lon, distance_km):

    segment_km = distance_km / 4

    east = (
        start_lat,
        start_lon + segment_km / (111 * max(0.01, abs(__import__("math").cos(__import__("math").radians(start_lat)))))
    )

    north = (start_lat + segment_km / 111, east[1])
    west = (north[0], start_lon)

    # Larger search radius for longer loops
    G = ox.graph_from_point(
        (start_lat, start_lon),
        dist=max(distance_km * 700, 3000),
        network_type="walk",
        simplify=True
    )

    start_node = ox.distance.nearest_nodes(
        G, start_lon, start_lat
    )

    east_node = ox.distance.nearest_nodes(
        G, east[1], east[0]
    )

    north_node = ox.distance.nearest_nodes(
        G, north[1], north[0]
    )

    west_node = ox.distance.nearest_nodes(
        G, west[1], west[0]
    )

    nodes_sequence = [
        start_node,
        east_node,
        north_node,
        west_node,
        start_node
    ]

    route = []
    total_length = 0

    for i in range(len(nodes_sequence) - 1):

        path = nx.shortest_path(
            G,
            nodes_sequence[i],
            nodes_sequence[i + 1],
            weight="length"
        )

        route.extend(path[:-1])

        total_length += nx.path_weight(
            G,
            path,
            weight="length"
        )

    route.append(start_node)

    return G, route, total_length / 1000


def find_best_loop(lat, lon, target_km, tolerance=0.15, max_attempts=15):

    best_result = None
    best_difference = float("inf")

    for i in range(max_attempts):

        scale = 1 - (0.025 * i)
        try_km = target_km * scale

        try:
            G, route, actual_km = generate_simple_loop(
                lat, lon, try_km
            )

            difference = abs(actual_km - target_km)

            if difference < best_difference:
                best_difference = difference
                best_result = (G, route, actual_km)

            if difference <= tolerance:
                return G, route, actual_km

        except Exception:
            continue

    if best_result is None:
        raise RuntimeError(
            "Could not generate a loop. Try another starting point."
        )

    return best_result


def export_gpx(route_df):

    gpx = ET.Element(
        "gpx",
        version="1.1",
        creator="MyLoopApp"
    )

    trk = ET.SubElement(gpx, "trk")
    trkseg = ET.SubElement(trk, "trkseg")

    for _, row in route_df.iterrows():

        trkpt = ET.SubElement(
            trkseg,
            "trkpt",
            lat=str(row["lat"]),
            lon=str(row["lon"])
        )

        ET.SubElement(trkpt, "ele").text = "0"

    tree = ET.ElementTree(gpx)

    gpx_bytes = BytesIO()

    tree.write(
        gpx_bytes,
        encoding="utf-8",
        xml_declaration=True
    )

    return gpx_bytes.getvalue()


# -----------------------------
# Step 1: Detect Location
# -----------------------------
st.subheader("Step 1: Detect Your Location")

location = streamlit_geolocation()

if (
    location
    and location.get("latitude") is not None
    and location.get("longitude") is not None
):

    detected_lat = location["latitude"]
    detected_lon = location["longitude"]

    if not st.session_state.location_detected:
        st.session_state.map_center = [
            detected_lat,
            detected_lon
        ]

        st.session_state.map_zoom = 15

    st.session_state.location_detected = True

    if st.button("Use My Current Location"):

        st.session_state.latlon = (
            detected_lat,
            detected_lon
        )

        st.session_state.map_center = [
            detected_lat,
            detected_lon
        ]

        st.session_state.route_df = None
        st.rerun()

    st.success("Location detected.")

else:

    st.info(
        "Location unavailable. You can select a point on the map "
        "or enter coordinates manually."
    )


# -----------------------------
# Step 2: Manual Coordinates
# -----------------------------
st.subheader("Enter Coordinates Manually")

st.caption(
    "Enter latitude and longitude to select an exact starting point."
)

coord_col1, coord_col2 = st.columns(2)

with coord_col1:

    manual_lat = st.number_input(
        "Latitude",
        min_value=-90.0,
        max_value=90.0,
        value=float(st.session_state.map_center[0]),
        format="%.6f",
        key="manual_latitude"
    )

with coord_col2:

    manual_lon = st.number_input(
        "Longitude",
        min_value=-180.0,
        max_value=180.0,
        value=float(st.session_state.map_center[1]),
        format="%.6f",
        key="manual_longitude"
    )

if st.button("Use These Coordinates"):

    st.session_state.latlon = (
        manual_lat,
        manual_lon
    )

    st.session_state.map_center = [
        manual_lat,
        manual_lon
    ]

    st.session_state.map_zoom = 15
    st.session_state.route_df = None

    st.rerun()


# -----------------------------
# Step 3: Select Starting Point
# -----------------------------
st.subheader("Select a Starting Point on the Map")

if st.session_state.latlon is not None:

    map_center = list(st.session_state.latlon)

else:

    map_center = st.session_state.map_center


m = folium.Map(
    location=map_center,
    zoom_start=st.session_state.map_zoom
)

if st.session_state.location_detected:

    folium.CircleMarker(
        location=st.session_state.map_center,
        radius=7,
        color="blue",
        fill=True,
        fill_color="blue",
        fill_opacity=0.8,
        popup="Detected Location"
    ).add_to(m)


if st.session_state.latlon:

    folium.Marker(
        location=st.session_state.latlon,
        popup="Starting Point",
        icon=folium.Icon(
            color="green",
            icon="map-marker"
        )
    ).add_to(m)


if st.session_state.route_df is not None:

    folium.PolyLine(
        locations=st.session_state.route_df[
            ["lat", "lon"]
        ].values.tolist(),
        color="blue",
        weight=5
    ).add_to(m)

    mid_idx = len(st.session_state.route_df) // 2

    mid_point = st.session_state.route_df.iloc[mid_idx]

    folium.Marker(
        location=[
            mid_point["lat"] + 0.0005,
            mid_point["lon"] + 0.0005
        ],
        popup=f"Distance: {st.session_state.generated_km:.2f} km",
        icon=folium.DivIcon(
            html=f"""
            <div style='font-size:14pt;
                        color:black;
                        background:white;
                        padding:3px;
                        border-radius:5px;'>
                {st.session_state.generated_km:.2f} km
            </div>
            """
        )
    ).add_to(m)


click_result = st_folium(
    m,
    height=500,
    returned_objects=["last_clicked"],
    key="main-map"
)

if click_result and click_result.get("last_clicked"):

    clicked_lat = click_result["last_clicked"]["lat"]
    clicked_lon = click_result["last_clicked"]["lng"]

    clicked_point = (clicked_lat, clicked_lon)

    if clicked_point != st.session_state.latlon:

        st.session_state.latlon = clicked_point
        st.session_state.map_center = [
            clicked_lat,
            clicked_lon
        ]

        st.session_state.route_df = None
        st.rerun()


if st.session_state.latlon:

    st.success(
        f"Starting point: "
        f"{st.session_state.latlon[0]:.6f}, "
        f"{st.session_state.latlon[1]:.6f}"
    )


# -----------------------------
# Step 4: Choose Distance
# -----------------------------
if st.session_state.latlon:

    st.subheader("Choose Loop Distance")

    distance_km = st.slider(
        "Choose Loop Distance (km)",
        min_value=1.0,
        max_value=26.0,
        value=5.0,
        step=0.5
    )

    if st.button("Generate Running Loop"):

        lat, lon = st.session_state.latlon

        with st.spinner(
            f"Generating your {distance_km} km running loop..."
        ):

            try:

                G, route, actual_distance_km = find_best_loop(
                    lat,
                    lon,
                    distance_km
                )

                coords = [
                    (G.nodes[n]["y"], G.nodes[n]["x"])
                    for n in route
                ]

                route_df = pd.DataFrame(
                    coords,
                    columns=["lat", "lon"]
                )

                st.session_state.route_df = route_df

                st.session_state.generated_km = (
                    actual_distance_km
                )

                st.rerun()

            except Exception as e:

                st.error(f"Error generating route: {e}")


# -----------------------------
# Step 5: Download GPX
# -----------------------------
if st.session_state.route_df is not None:

    gpx_data = export_gpx(
        st.session_state.route_df
    )

    file_name = "running_loop.gpx"

    st.subheader("Download Your Running Route")

    st.metric(
        "Generated Distance",
        f"{st.session_state.generated_km:.2f} km"
    )

    st.download_button(
        label="Download GPX File",
        data=gpx_data,
        file_name=file_name,
        mime="application/gpx+xml"
    )

    st.markdown("---")

    st.markdown(
        """
        **Import into Komoot**

        1. Open [komoot.com/upload](https://www.komoot.com/upload).
        2. Upload your downloaded GPX file.

        On mobile:

        1. Open the Komoot app.
        2. Go to Profile → Routes → Import.
        3. Select the GPX file.
        """
    )
