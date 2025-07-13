import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from ecoscope.io.earthranger import EarthRangerIO
from pandas import json_normalize, to_datetime
import requests

#### ER AUTHENTICATION ###############################################
def er_login(username, password):
    try:
        er = EarthRangerIO(
            server="https://twiga.pamdas.org",
            username=username,
            password=password
        )
        er.get_subjects(limit=1)          # Try a simple call to check credentials
        return True
    except Exception:
        return False
    
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "password" not in st.session_state:
    st.session_state["password"] = ""

if not st.session_state["authenticated"]:
    st.title("Login to EarthRanger Dashboard")
    username = st.text_input("EarthRanger Username")
    password = st.text_input("EarthRanger Password", type="password")
    if st.button("Login"):
        if er_login(username, password):
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.session_state["password"] = password
            st.success("Login successful!")
            st.rerun()   # force restart to load app
        else:
            st.error("Invalid credentials. Please try again.")
    st.stop()

username = st.session_state["username"]  # save for authentication later
password = st.session_state["password"]  # save for authentication later







#### PULL DATA ###################################
# get list of active NANW giraffe subjects
@st.cache_data(ttl=3600)
def get_active_nanw_subjects(): 
    er = EarthRangerIO(
        server="https://twiga.pamdas.org",
        username=username,
        password=password
    )
    subjects_df = er.get_subjects(subject_group_id="518a21df-46a0-4dfb-90de-54e1caca889e")
    subjects = subjects_df.to_dict('records')
    active = [s for s in subjects if s.get("is_active") is True]
    return active

# get list of active Adopt A Giraffe giraffe subjects
@st.cache_data(ttl=3600)
def get_active_aag_subjects():   
    er = EarthRangerIO(
        server="https://twiga.pamdas.org",
        username=username,
        password=password
    )
    subjects_df = er.get_subjects(subject_group_id="660dbfb0-a7cb-4b93-92e9-a8f006f9bead")
    subjects = subjects_df.to_dict('records')
    return subjects

active_subjects = get_active_nanw_subjects()
aag_subjects = get_active_aag_subjects()
aag_id_to_name = {s["id"]: s["name"] for s in aag_subjects if "id" in s and "name" in s}
aag_ids = set(aag_id_to_name.keys())


# get giraffe nw monitoring events
@st.cache_data(ttl=3600)
def load_data():
    er = EarthRangerIO(
        server="https://twiga.pamdas.org",
        username=username,
        password=password
    )
    event_cat = "monitoring_nanw"
    event_type = "giraffe_nw_monitoring"
    since = "2024-07-01T00:00:00Z"
    until = datetime.utcnow().isoformat(timespec="seconds") + "Z"  # always till now sys.date
    events = er.get_events(
        event_category=event_cat,
        since=since,
        until=until,
        include_details=True,
        include_notes=False
    )
    flat = json_normalize(events.to_dict(orient="records"))
    giraffe_only = flat[flat["event_type"] == event_type]

    giraffe_only = giraffe_only.explode("event_details.Herd").reset_index(drop=True)  # explore nested herd details
    herd_df = json_normalize(giraffe_only["event_details.Herd"])
    events_final = pd.concat([giraffe_only.drop(columns="event_details.Herd"), herd_df], axis=1)

    return events_final

df = load_data()

# rename columns for clarity
rename_map = {
    "reported_by.id": "user_id",
    "reported_by.name": "user_name",
    "id": "event_id",
    "event_type": "evt_type",
    "event_category": "evt_category",
    "serial_number": "evt_serial",
    "url": "evt_url",
    "time": "evt_dttm",
    "location.latitude": "lat",
    "location.longitude": "lon",
    "event_details.image_prefix": "evt_imagePrefix",
    "event_details.herd_dire": "evt_herd_dir",
    "event_details.herd_dist": "evt_herd_dist",
    "event_details.herd_size": "evt_herdSize",
    "event_details.herd_notes": "evt_herdNotes",
    "giraffe_id": "evt_girID",
    "giraffe_age": "evt_girAge",
    "giraffe_gsd": "evt_girGSD",
    "giraffe_sex": "evt_girSex",
    "giraffe_dire": "evt_girDire",
    "giraffe_dist": "evt_girDist",
    "giraffe_snar": "evt_girSnare",
    "giraffe_notes": "evt_girNotes",
    "giraffe_right": "evt_girRight",
    "giraffe_left": "evt_gifLeft",
    "giraffe_gsd_loc": "evt_girGSD_loc",
    "giraffe_gsd_sev": "evt_girGSD_sev",
    "event_details.river_system": "evt_riverSystem"
}

df = df.rename(columns=rename_map)
df["evt_dttm"] = pd.to_datetime(df["evt_dttm"])
df = df.dropna(subset=["evt_dttm"])



#### DASHBOARD LAYOUT ###############################################
# sidebar filter
st.sidebar.header("Filter Date Range")

df["evt_dttm"] = pd.to_datetime(df["evt_dttm"], errors="coerce")
df = df.dropna(subset=["evt_dttm"])   # clean evt_dttm and drop na values
if df["evt_dttm"].notna().any():
    min_date = df["evt_dttm"].min().date()
    max_date = df["evt_dttm"].max().date()
else:
    min_date = datetime.today().date()
    max_date = datetime.today().date()

date_range = st.sidebar.date_input("Select date range", [min_date, max_date]) # filter data by selected date range
filtered_df = df[(df["evt_dttm"].dt.date >= date_range[0]) & (df["evt_dttm"].dt.date <= date_range[1])]


st.title("🦒 GCF Namibia NW monitoring")  # main heading

# header metrics
st.sidebar.metric("Current population size", len(active_subjects)) # shown in side bar separately

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Distinct individuals seen", df["evt_girID"].nunique()) # unique individuals seen
with col2:
    herd_count = filtered_df["evt_herdSize"].count()  # unique herds seen
    st.metric("Herds seen", herd_count)
with col3:
    avg_herd_size = filtered_df["evt_herdSize"].mean()  # mean herd size
    st.metric("Average herd size", f"{avg_herd_size:.1f}" if not pd.isna(avg_herd_size) else "N/A")

# sighting map
st.subheader("📍 Sighting Map")
map_df = filtered_df.dropna(subset=["lat", "lon"])
st.map(map_df[["lat", "lon"]])

# sightings/month bar chart
st.subheader("📅 Sightings per Month")
monthly_counts = (
    filtered_df.groupby(filtered_df["evt_dttm"].dt.to_period("M"))
    .size()
    .reset_index(name="Sightings")
)
monthly_counts["Month"] = monthly_counts["evt_dttm"].astype(str)
fig1 = px.bar(monthly_counts, x="Month", y="Sightings", title="Monthly Sightings")
st.plotly_chart(fig1, use_container_width=True)

# age/sex breakdown bar chart
st.subheader("🧬 Age / Sex Breakdown")
breakdown = (
    filtered_df.groupby(["evt_girSex", "evt_girAge"])
    .size()
    .reset_index(name="Count")
)
fig2 = px.bar(breakdown, x="evt_girAge", y="Count", color="evt_girSex", barmode="group")
st.plotly_chart(fig2, use_container_width=True)

# table of seen giraffe names 
st.subheader("🦒 List of giraffe seen")
id_to_name = {s["id"]: s["name"] for s in active_subjects if "id" in s and "name" in s}   # Build a mapping from subject ID to name
filtered_df["giraffe_name"] = filtered_df["evt_girID"].map(id_to_name)   # Map evt_girID to giraffe name
girid_table = (
    filtered_df[["evt_girID", "giraffe_name"]]
    .drop_duplicates()
    .sort_values("giraffe_name")
    .reset_index(drop=True)
)
st.dataframe(girid_table[["giraffe_name"]].drop_duplicates().sort_values("giraffe_name").reset_index(drop=True), use_container_width=True)

# table of seen Adopt A Giraffe giraffe  
aag_seen = filtered_df[filtered_df["evt_girID"].isin(aag_ids)].copy()
aag_seen["giraffe_name"] = aag_seen["evt_girID"].map(aag_id_to_name)
aag_table = (
    aag_seen[["evt_girID", "giraffe_name"]]
    .drop_duplicates()
    .sort_values("giraffe_name")
    .reset_index(drop=True)
)
st.subheader("🦒 List of AAG giraffe seen")
if not aag_table.empty:
    st.dataframe(aag_table[["giraffe_name"]].drop_duplicates().sort_values("giraffe_name").reset_index(drop=True), use_container_width=True)
else:
    st.info("No AAG giraffes seen in the selected data.")
