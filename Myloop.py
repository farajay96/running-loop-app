st.subheader("Enter Coordinates Manually")

col1, col2 = st.columns(2)

with col1:
    manual_lat = st.number_input(
        "Latitude",
        min_value=-90.0,
        max_value=90.0,
        value=24.7136,
        format="%.6f"
    )

with col2:
    manual_lon = st.number_input(
        "Longitude",
        min_value=-180.0,
        max_value=180.0,
        value=46.6753,
        format="%.6f"
    )

if st.button("Use These Coordinates"):
    st.session_state.latlon = (manual_lat, manual_lon)
    st.session_state.route_df = None
    st.rerun()
