import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
import json
import copy
import random
from modules.farm import Farm, Batch

# Placeholder classes and functions from your notebook
# Include Batch, Farm, create_species_df, plot_farm_totals, plot_additions_stacked, etc.

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

# Streamlit app layout
st.title("Coral Production Planning App")

# Configuration Section
st.sidebar.header("Configuration")
# Production Order Input
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
forecast_days = st.sidebar.number_input("Forecast Days", min_value=1, max_value=365, value=365)

# Initialize batches (mock or fetch from data source)
st.sidebar.header("Initialization")
use_mock_data = st.sidebar.checkbox("Use Mock Data", value=True)

if use_mock_data:
    st.sidebar.write("Generating mock data for demonstration purposes.")
    batches_list = []
    for i in range(5):
        species = random.choice(list(production_order.keys()))
        batch = Batch(
            batch_id=f"TEST-{i}",
            species=species,
            quantity=farm_config["MAX_BATCH_QUANTITY"],
            stage="BS",
            start_date=0,
        )
        batches_list.append(batch)
else:
    st.sidebar.write("Add your data fetching logic here.")
    batches_list = []  # Replace with fetched batches

# Display Configuration and Initialization
st.subheader("Current Configuration")
st.json(production_order)
st.json(farm_config)

# Forecasting and Planning
st.header("Run Forecast and Production Planning")
if st.button("Run"):
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
    forecast_result = my_farm.forecast(days=forecast_days, production_order=production_order, desired_output=sum(production_order.values()))
    forecasted_totals = pd.DataFrame([total['overall'] for total in forecast_result[1]])
    forecasted_totals["Day"] = forecasted_totals.index
    st.line_chart(forecasted_totals[["Day", "BS", "MF", "FS", "OP"]].set_index("Day"))

    # Hypothetical Planning
    st.subheader("Production Plan")
    final_shortfall_species = {spec: forecast_result[1][-1]["species"][spec]["SF"] for spec in production_order.keys()}
    hypothetical_result = my_farm.plan_future(forecast_days, final_shortfall_species, forecast_result[3])
    hypothetical_totals = pd.DataFrame([total['overall'] for total in hypothetical_result[1]])
    hypothetical_totals["Day"] = hypothetical_totals.index
    st.line_chart(hypothetical_totals[["Day", "BS", "MF", "FS", "OP"]].set_index("Day"))

    # Visualization
    st.subheader("Weekly Production Changes")
    additions = pd.DataFrame([total['overall'] for total in hypothetical_result[2]])
    additions["Week"] = additions.index // 7
    weekly_additions = additions.groupby("Week").sum()
    st.bar_chart(weekly_additions[["BS", "MF", "FS", "OP"]])

# Footer
st.write("Developed by Coral Restoration Team.")