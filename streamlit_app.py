import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
import json
import copy
import random
from modules.farm import Farm, Batch
from modules.bigquery_util import current_data, row_to_batch

def combine_and_style_compliance_table(plan, compliance):
    """
    Combine the plan and compliance data into a single table with styled compliance cells.

    Parameters:
        plan (pd.DataFrame): Planned production targets.
        compliance (pd.DataFrame): Mock compliance data.

    Returns:
        pd.DataFrame.style: Styled DataFrame combining plan and compliance.
    """
    # Combine plan and compliance into a single table
    combined = plan.copy()

    # Add "_Plan" and "_Compliance" columns
    for col in ["BS", "MF", "FS", "OP"]:
        if col in plan.columns:
            combined[f"{col}_Plan"] = plan[col]
            combined[f"{col}_Compliance"] = compliance[col]

    # Drop original columns
    combined = combined.drop(columns=["BS", "MF", "FS", "OP"])

    # Helper function to style compliance cells
    def style_cells(row, col_name):
        if "_Compliance" in col_name:
            plan_col = col_name.replace("_Compliance", "_Plan")
            plan_value = row[plan_col]
            compliance_value = row[col_name]
            if compliance_value == 0:
                return ""  # Do not style cells with a value of 0
            elif compliance_value < plan_value:
                return "background-color: #ff9999;"  # Red for below plan
            elif compliance_value >= plan_value:
                return "background-color: #006400; color: white;"  # Green for at/above plan
        return ""

    # Apply styling to compliance columns only
    styled_table = combined.style.apply(
        lambda row: [
            style_cells(row, col) if "_Compliance" in col else "" for col in combined.columns
        ],
        axis=1,
    )

    return styled_table

def create_unified_result(forecast_result, hypothetical_result):
    """
    Combine forecast_result and hypothetical_result into a unified result.

    Parameters:
        forecast_result (tuple): The result from the forecast function, consisting of 
                                 (rolling_inventory, rolling_totals, rolling_changes, rolling_capacity).
        hypothetical_result (tuple): The result from the hypothetical (shortfall recovery) function, consisting of 
                                      (rolling_inventory, rolling_totals, rolling_changes, rolling_capacity).

    Returns:
        tuple: Unified result in the same format as forecast_result and hypothetical_result.
    """
    def merge_lists(list1, list2, is_capacity=False):
        merged = []
        for day_data1, day_data2 in zip(list1, list2):
            if not is_capacity:
                # Regular merge for totals and changes
                merged_day = {
                    "overall": {
                        key: day_data1["overall"].get(key, 0) + day_data2["overall"].get(key, 0)
                        for key in set(day_data1["overall"]) | set(day_data2["overall"])
                    },
                    "species": {
                        species: {
                            key: day_data1["species"].get(species, {}).get(key, 0) +
                                 day_data2["species"].get(species, {}).get(key, 0)
                            for key in set(day_data1["species"].get(species, {})) | set(day_data2["species"].get(species, {}))
                        }
                        for species in set(day_data1["species"]) | set(day_data2["species"])
                    }
                }
            else:
                # Special merge for capacity
                merged_day = {
                    "overall": day_data1["overall"] + day_data2["overall"],
                    "stage": {
                        stage: day_data1["stage"].get(stage, 0) + day_data2["stage"].get(stage, 0)
                        for stage in set(day_data1["stage"]) | set(day_data2["stage"])
                    }
                }
            merged.append(merged_day)
        return merged

    unified_inventory = hypothetical_result[0]  # Use hypothetical inventory directly
    unified_totals = merge_lists(forecast_result[1], hypothetical_result[1])
    unified_changes = merge_lists(forecast_result[2], hypothetical_result[2])
    unified_capacity = hypothetical_result[3]

    return unified_inventory, unified_totals, unified_changes, unified_capacity

def merge_forecast_and_recovery(forecast_fin, shortfall_recovery_fin):
    """
    Merge the forecast FIN and shortfall recovery FIN into a unified FIN.

    Parameters:
        forecast_fin (pd.DataFrame): Forecasted farm inventory numbers.
        shortfall_recovery_fin (pd.DataFrame): Shortfall recovery farm inventory numbers.

    Returns:
        pd.DataFrame: Unified FIN combining forecast and recovery plans.
    """
    unified_fin = forecast_fin.copy()

    # Add shortfall recovery numbers where applicable
    for col in ["BS", "MF", "FS", "OP"]:
        if col in shortfall_recovery_fin.columns:
            unified_fin[col] = unified_fin[col] + shortfall_recovery_fin[col]

    return unified_fin

def generate_mock_compliance_data(planned: pd.DataFrame) -> pd.DataFrame:
    """
    Generate mock compliance data based on planned production data.

    Parameters:
        planned (pd.DataFrame): Planned production data.

    Returns:
        pd.DataFrame: Mock compliance data with random deviations.
    """
    def mock_value(plan_value):
        if plan_value == 0:
            return 0  # Keep as zero if planned value is zero
        # Randomly generate a mock value above, equal, or below the planned value
        deviation = random.choice([-1, 0, 1])
        return max(0, plan_value + deviation * random.randint(1, 5))

    # Apply the mock value function to all relevant cells
    mock_data = planned.copy()
    for col in ["BS", "MF", "FS", "OP"]:
        if col in planned.columns:
            mock_data[col] = planned[col].apply(mock_value)

    return mock_data

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

page = st.sidebar.selectbox("Choose a page", ["Production Planning", "Compliance"])


# Highlight instructions using markdown
if page == "Production Planning": 
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
    st.subheader("Current Inventory Forecast")
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
    st.subheader("Shortfall Plan (hypothetical new broodstock and their forcast)")
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

    # Display shortfall recovery only
    st.line_chart(
        hypothetical_totals.set_index("Day")[["BS", "MF", "FS", "OP"]],
        use_container_width=True,
        height=300
    )

    # Weekly Production Changes for Overall Plan
    st.subheader("Production Plan (Current Inventory + Hypothetical BS Forcast)")
    # Generate unified FIN
    unified_result = create_unified_result(forecast_result, hypothetical_result)

    # Prepare data for overall totals
    unified_totals_ = pd.DataFrame([total['overall'] for total in unified_result[1]])
    unified_totals_["Day"] = unified_totals_.index
    st.line_chart(
        unified_totals_.set_index("Day")[["BS", "MF", "FS", "OP"]],
        use_container_width=True,
        height=300
    )

    unified_changes = pd.DataFrame([total["overall"] for total in unified_result[2]])

    # Weekly Production Changes for Overall Plan
    st.subheader("Production Plan Weekly Changes")
    unified_changes["Week"] = unified_changes.index // 7
    weekly_changes = unified_changes.groupby("Week").sum()
    st.bar_chart(weekly_changes[["BS", "MF", "FS", "OP"]])

    # Weekly Production Changes for Overall Plan
    st.subheader("Production Plan Farm Capacity Occupied")
    unified_capacity = pd.DataFrame([(farm_config["TANK_CAPACITY"] * farm_config["NUM_PROD_TANKS"]) - total["overall"] for total in unified_result[3]])
    unified_capacity["Week"] = unified_capacity.index // 7
    weekly_capacity_avail = unified_capacity.groupby("Week").max()
    st.bar_chart(weekly_capacity_avail)

    unified_species_totals = pd.DataFrame([
        {"Day": i, "Species": species, **data}
        for i, daily in enumerate(unified_result[1])
        for species, data in daily["species"].items()
    ])
    unified_species_changes = pd.DataFrame([
        {"Day": i, "Species": species, **data}
        for i, daily in enumerate(unified_result[2])
        for species, data in daily["species"].items()
    ])

    # Compliance View: Weekly Production Targets
    st.subheader("Weekly Production Compliance View")

    # Group by week and species
    unified_species_changes["Week"] = unified_species_changes["Day"] // 7
    weekly_plan = unified_species_changes.groupby(["Week", "Species"])[
        ["BS", "MF", "FS", "OP"]
    ].sum().reset_index()

    # Generate mock compliance data
    weekly_compliance = generate_mock_compliance_data(weekly_plan)

    # Combine and style the table
    styled_weekly_table = combine_and_style_compliance_table(weekly_plan, weekly_compliance)

    # Display the styled table
    st.dataframe(styled_weekly_table, height=600)

    # Compliance View: Daily Production Targets
    st.subheader("Daily Production Compliance View")

    # Prepare daily production targets by species
    daily_production_targets = unified_species_changes.groupby(["Day", "Species"])[
        ["BS", "MF", "FS", "OP"]
    ].sum().reset_index()

    daily_quantity_targets = unified_species_totals.groupby(["Day", "Species"])[
        ["BS", "MF", "FS", "OP"]
    ].sum().reset_index()

    # Display the table in Streamlit
    st.write("The table below shows the daily production targets for each species and batch type:")
    st.dataframe(daily_production_targets)

# Footer
st.write("Developed by BrainCoral Dev Team.")