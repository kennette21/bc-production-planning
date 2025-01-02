import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
import json
import copy
import random
from modules.farm import Farm, Batch
from modules.bigquery_util import current_data, row_to_batch

# Helper functions to initialize default parameters
def default_production_order():
    return {'PAST': 7000, 'APAL': 6000, 'APRO': 6000, 'PCLI': 3000, 'ACER': 5000}

def default_farm_config():
    return {
        "NUM_PROD_TANKS": 27,
        "TANK_CAPACITY": 1000,
        "STAGE_CAPACITIES": {"BS": 1000, "MF": 300, "FS": 300, "OP": 1000},
        "DEFAULT_BS_QUANTITY": 100,
        "MAX_BATCH_QUANTITY": 100,
        "BS_CYCLE_DAYS": 28,
        "MF_CYCLE_DAYS": 30,
        "FS_CYCLE_DAYS": 90,
        "BS_MORTALITY_STD": 0.05,
        "MF_MORTALITY_STD": 0.1,
        "FS_MORTALITY_STD": 0.05,
    }


# Highlight instructions using markdown
st.sidebar.markdown(
    """
    <style>
    .important {
        background-color: #FFFACD;
        color: #000;
        font-weight: bold;
        padding: 10px;
        border-radius: 5px;
    }
    </style>
    <div class="important">
    ⚠️ Remember: Updating these values will change the forecast and plan!
    </div>
    """,
    unsafe_allow_html=True,
)

# Streamlit app layout
st.title("Coral Production Planning App")

# Configuration Section
st.sidebar.title("🔧 Configuration")
st.sidebar.markdown(
    """
    **Customize the production parameters here.**
    Adjust the values to see how they affect the forecast and production plan!
    """
)
# Production Order Input
st.sidebar.header("📋 Production Order")
production_order_input = st.sidebar.text_area(
    "Production Order (JSON)",
    value=json.dumps(default_production_order(), indent=4),
    height=200
)
try:
    production_order = json.loads(production_order_input)
except json.JSONDecodeError:
    st.sidebar.error("Invalid JSON for Production Order.")
    production_order = default_production_order()

# Farm Configuration Input
st.sidebar.header("🏗️ Farm Configuration")
farm_config_input = st.sidebar.text_area(
    "Farm Configuration (JSON)",
    value=json.dumps(default_farm_config(), indent=4),
    height=300
)
try:
    farm_config = json.loads(farm_config_input)
except json.JSONDecodeError:
    st.sidebar.error("Invalid JSON for Farm Configuration.")
    farm_config = default_farm_config()

# Forecast Days
st.sidebar.header("📆 Forecast Settings")
forecast_days = st.sidebar.number_input("Forecast Days", min_value=1, max_value=365, value=365)

# Initialize batches (mock or fetch from data source)
st.sidebar.header("🚀 Initialization")
# Radio button for selecting data source
data_source = st.sidebar.radio(
    "Choose Data Source",
    options=["Use Mock Data", "Fetch from BigQuery"],
    index=0,
    help="Select whether to use mock data for demonstration or fetch live data from BigQuery."
)

# Conditional logic for data source selection
if data_source == "Fetch from BigQuery":
    st.sidebar.write("Fetching data from BigQuery...")
    try:
        df_current = current_data()  # Fetch data from BigQuery
        batches_list = [row_to_batch(row) for _, row in df_current.iterrows()]
        st.sidebar.success("Data fetched and processed successfully!")
    except Exception as e:
        st.sidebar.error(f"Error fetching data: {e}")
        batches_list = []  # Fallback to empty list
else:
    st.sidebar.write("Using mock data for demonstration.")
    batches_list = []
    for i in range(5):
        species = random.choice(list(default_production_order().keys()))
        batch = Batch(
            batch_id=f"TEST-{i}",
            species=species,
            quantity=100,
            stage="BS",
            start_date=0,
        )
        batches_list.append(batch)

# Display Configuration and Initialization
st.subheader("Current Configuration")
st.json(production_order)
st.json(farm_config)

# Forecasting and Planning Section
st.header("Run Forecast and Production Planning")
# Add Prominent RUN Button
st.markdown(
    """
    <style>
    div.stButton > button {
        width: 100%;
        padding: 15px;
        font-size: 18px;
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        border-radius: 8px;
    }
    div.stButton > button:hover {
        background-color: #45a049;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


if st.button("🚀 Run Forecast and Planning"):
    # Initialize farm
    my_farm = Farm(
        inventory=batches_list,
        tank_capacity=farm_config["TANK_CAPACITY"],
        tank_num=farm_config["NUM_PROD_TANKS"],
        stage_capacities=farm_config["STAGE_CAPACITIES"],
        production_order=production_order,
    )

    # Run forecast
    st.subheader("Forecast Results")
    forecast_result = my_farm.forecast(
        days=forecast_days,
        production_order=production_order,
        desired_output=sum(production_order.values())
    )
    # Prepare data for overall totals
    forecasted_totals = pd.DataFrame([total['overall'] for total in forecast_result[1]])
    forecasted_totals["Day"] = forecasted_totals.index

    # Display overall forecast
    st.line_chart(
        forecasted_totals.set_index("Day")[["BS", "MF", "FS", "OP"]],
        use_container_width=True,
        height=300
    )

    # Hypothetical Planning
    st.subheader("Production Plan")
    final_shortfall_species = {
        spec: forecast_result[1][-1]["species"].get(spec, {}).get("SF", 0)
        for spec in production_order.keys()
    }
    hypothetical_result = my_farm.plan_future(
        forecast_days, final_shortfall_species, forecast_result[3]
    )

    # Prepare data for overall production plan totals
    hypothetical_totals = pd.DataFrame([total["overall"] for total in hypothetical_result[1]])
    hypothetical_totals["Day"] = hypothetical_totals.index

    # Display overall production plan
    st.line_chart(
        hypothetical_totals.set_index("Day")[["BS", "MF", "FS", "OP"]],
        use_container_width=True,
        height=300
    )

    # Weekly Production Changes for Overall Plan
    st.subheader("Weekly Production Changes (Overall)")
    hypothetical_changes = pd.DataFrame([total["overall"] for total in hypothetical_result[2]])
    hypothetical_changes["Week"] = hypothetical_changes.index // 7
    weekly_changes = hypothetical_changes.groupby("Week").sum()
    st.bar_chart(weekly_changes[["BS", "MF", "FS", "OP"]])

    # Prepare species-specific data
    forecasted_species_totals = pd.DataFrame([
        {"Day": i, "Species": species, **data}
        for i, daily in enumerate(forecast_result[1])
        for species, data in daily["species"].items()
    ])
    hypothetical_species_totals = pd.DataFrame([
        {"Day": i, "Species": species, **data}
        for i, daily in enumerate(hypothetical_result[1])
        for species, data in daily["species"].items()
    ])
    hypothetical_species_changes = pd.DataFrame([
        {"Day": i, "Species": species, **data}
        for i, daily in enumerate(hypothetical_result[2])
        for species, data in daily["species"].items()
    ])

    # Display species-specific graphs
    st.subheader("Species-Specific Graphs")
    species_list = forecasted_species_totals["Species"].unique()

    for species in species_list:
        with st.expander(f"Graphs for {species}"):
            # Species-specific production plan
            species_plan_data = hypothetical_species_totals[
                hypothetical_species_totals["Species"] == species
            ]
            st.line_chart(
                species_plan_data.set_index("Day")[["BS", "MF", "FS", "OP"]],
                use_container_width=True
            )

            # Weekly production changes for species
            species_changes = hypothetical_species_changes[
                hypothetical_species_changes["Species"] == species
            ]
            species_changes["Week"] = species_changes["Day"] // 7
            weekly_species_changes = species_changes.groupby("Week").sum()
            st.bar_chart(weekly_species_changes[["BS", "MF", "FS", "OP"]])

    # Compliance View: Weekly Production Targets
    st.subheader("Weekly Production Compliance View")

    # Prepare weekly production targets by species
    hypothetical_species_changes["Week"] = hypothetical_species_changes["Day"] // 7
    weekly_production_targets = hypothetical_species_changes.groupby(["Week", "Species"])[
        ["BS", "MF", "FS", "OP"]
    ].sum().reset_index()

    # Display the table in Streamlit
    st.write("The table below shows the weekly production targets for each species and batch type:")
    st.dataframe(weekly_production_targets)

    # Add CSV download option
    @st.cache_data
    def convert_df_to_csv(df):
        return df.to_csv(index=False).encode("utf-8")

    csv_data = convert_df_to_csv(weekly_production_targets)
    st.download_button(
        label="Download Weekly Production Targets as CSV",
        data=csv_data,
        file_name="weekly_production_targets.csv",
        mime="text/csv",
    )

    # Compliance View: Daily Production Targets
    st.subheader("Daily Production Compliance View")

    # Prepare daily production targets by species
    daily_production_targets = hypothetical_species_changes.groupby(["Day", "Species"])[
        ["BS", "MF", "FS", "OP"]
    ].sum().reset_index()

    # Display the table in Streamlit
    st.write("The table below shows the daily production targets for each species and batch type:")
    st.dataframe(daily_production_targets)

    csv_data_daily = convert_df_to_csv(daily_production_targets)
    st.download_button(
        label="Download Daily Production Targets as CSV",
        data=csv_data_daily,
        file_name="daily_production_targets.csv",
        mime="text/csv",
    )

# Footer
st.write("Developed by BrainCoral Dev Team.")