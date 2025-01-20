import streamlit as st
import pandas as pd
import json
from modules.farm import Farm, Batch
from modules.bigquery_util import current_data, row_to_batch, save_production_plan_to_bigquery
from modules.utils import (
    default_production_order,
    default_farm_config,
    create_unified_result
)

def forecast_page():
    st.title("Production Planning")

    # Configuration Section
    st.sidebar.title("🔧 Configuration")

    st.sidebar.markdown(
        """
        <style>
        .important {
            background-color: #FFFACD;
            color: #000;
            font-weight: bold;
            padding: 10px;
            border-radius: 5px;
        </style>
        <div class="important">
        ⚠️ Remember: Updating these values will change the forecast and plan!
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar Inputs
    production_order_input = st.sidebar.text_area(
        "Production Order (JSON)",
        value=json.dumps(default_production_order(), indent=4),
        height=200,
    )
    try:
        production_order = json.loads(production_order_input)
    except json.JSONDecodeError:
        st.sidebar.error("Invalid JSON for Production Order.")
        production_order = default_production_order()

    farm_config_input = st.sidebar.text_area(
        "Farm Configuration (JSON)",
        value=json.dumps(default_farm_config(), indent=4),
        height=300,
    )
    try:
        farm_config = json.loads(farm_config_input)
    except json.JSONDecodeError:
        st.sidebar.error("Invalid JSON for Farm Configuration.")
        farm_config = default_farm_config()

    forecast_days = st.sidebar.number_input("Forecast Days", min_value=1, max_value=365, value=365)

    # Radio button for selecting data source
    data_source = st.sidebar.radio(
        "Choose Data Source",
        options=["Use Mock Data", "Fetch from BigQuery"],
        index=0,
    )

    # Initialize batches
    batches_list = []
    if data_source == "Fetch from BigQuery":
        st.sidebar.write("Fetching data from BigQuery...")
        try:
            df_current = current_data()
            batches_list = [row_to_batch(row) for _, row in df_current.iterrows()]
            st.sidebar.success("Data fetched successfully!")
        except Exception as e:
            st.sidebar.error(f"Error fetching data: {e}")
    else:
        for i in range(5):
            species = list(default_production_order().keys())[i % 5]
            batches_list.append(Batch(batch_id=f"TEST-{i}", species=species, quantity=100, stage="BS", start_date=0))

    # Run Forecast and Planning
    if st.button("🚀 Run Forecast and Planning"):
        my_farm = Farm(
            inventory=batches_list,
            tank_capacity=farm_config["TANK_CAPACITY"],
            tank_num=farm_config["NUM_PROD_TANKS"],
            stage_capacities=farm_config["STAGE_CAPACITIES"],
            production_order=production_order,
        )

        # Forecast and Hypothetical Planning
        forecast_result = my_farm.forecast(forecast_days, production_order, sum(production_order.values()))
        final_shortfall_species = {
            spec: forecast_result[1][-1]["species"].get(spec, {}).get("SF", 0)
            for spec in production_order.keys()
        }
        hypothetical_result = my_farm.plan_future(forecast_days, final_shortfall_species, forecast_result[3])
        unified_result = create_unified_result(forecast_result, hypothetical_result)

        # Save unified_result to session state
        st.session_state.unified_result = unified_result

        # Forecast Graph
        st.subheader("Current Inventory Forecast")
        forecast_totals = pd.DataFrame([total["overall"] for total in forecast_result[1]])
        forecast_totals["Day"] = forecast_totals.index
        st.line_chart(forecast_totals.set_index("Day")[["BS", "MF", "FS", "OP"]])

        # Hypothetical Graph
        st.subheader("Shortfall Recovery Plan")
        hypothetical_totals = pd.DataFrame([total["overall"] for total in hypothetical_result[1]])
        hypothetical_totals["Day"] = hypothetical_totals.index
        st.line_chart(hypothetical_totals.set_index("Day")[["BS", "MF", "FS", "OP"]])

        # Unified Plan Graph
        st.subheader("Unified Production Plan")
        unified_totals = pd.DataFrame([total["overall"] for total in unified_result[1]])
        unified_totals["Day"] = unified_totals.index
        st.line_chart(unified_totals.set_index("Day")[["BS", "MF", "FS", "OP"]])

    # Save Unified Plan
    st.subheader("Save Unified Production Plan")
    plan_name = st.text_input("Enter a name for the production plan:", "")
    if st.button("💾 Save Production Plan", key="save_plan_button") and plan_name.strip():
        if "unified_result" in st.session_state:
            result_message = save_production_plan_to_bigquery(plan_name, st.session_state.unified_result)
            st.success(result_message)
        else:
            st.error("No unified result to save. Please run the forecast first.")