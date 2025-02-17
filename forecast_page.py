import streamlit as st
import pandas as pd
import json
from google.cloud import bigquery
from google.oauth2 import service_account
from datetime import datetime
from modules.farm import Farm, Batch
from modules.bigquery_util import current_data, historical_data, row_to_batch, save_production_plan_to_bigquery
from modules.utils import (
    default_production_order,
    default_farm_config,
    create_unified_result
)

# Create API client.
credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"]
)
bigQclient = bigquery.Client(credentials=credentials)

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

    tenant_option = st.sidebar.radio(
            "Select Tenant",
            options=["saudi", "freeport"],
            index=0,
        )

    # Sidebar Inputs
    production_order_input = st.sidebar.text_area(
        "Production Order (JSON)",
        value=json.dumps(default_production_order(tenant_option), indent=4),
        height=200,
    )
    try:
        production_order = json.loads(production_order_input)
    except json.JSONDecodeError:
        st.sidebar.error("Invalid JSON for Production Order.")
        production_order = default_production_order()

    farm_config_input = st.sidebar.text_area(
        "Farm Configuration (JSON)",
        value=json.dumps(default_farm_config(tenant_option), indent=4),
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
       # Add a placeholder option to force user selection
        date_option = st.sidebar.radio(
            "Select Date Option",
            options=["Select an Option", "Current Date", "Enter a Specific Date"],
            index=0,
        )

        # Ensure user makes a choice before running queries
        if date_option == "Current Date":
            selected_datetime = datetime.now().date()
            selected_date = selected_datetime.strftime("%Y-%m-%d")
            try:
                df_batches = current_data(bigQclient, tenant_option)  # Fetch current data
                batches_list = [row_to_batch(row) for _, row in df_batches.iterrows()]
                st.sidebar.success("Data fetched successfully!")
            except Exception as e:
                st.sidebar.error(f"Error fetching data: {e}")

        elif date_option == "Enter a Specific Date":
            selected_datetime = st.sidebar.date_input("Start Date of Production Plan", datetime.now())
            selected_date = selected_datetime.strftime("%Y-%m-%d")
            if selected_date:  # Ensure a date is entered before fetching
                try:
                    df_batches = historical_data(bigQclient, selected_date, tenant_option)  # Fetch historical data
                    batches_list = [row_to_batch(row) for _, row in df_batches.iterrows()]
                    st.sidebar.success("Data fetched successfully!")
                except Exception as e:
                    st.sidebar.error(f"Error fetching data: {e}")
    else:
        selected_datetime = datetime.now().date()
        for i in range(0):
            species = list(default_production_order(tenant_option).keys())[i % 5]
            batches_list.append(Batch(batch_id=f"TEST-{i}", species=species, quantity=100, stage="BS", start_date=0))

    # No Outplant start and end
    no_outplant_start_date = st.sidebar.date_input("Start Date of \"No Outplant Period\"", datetime.now())
    no_outplant_end_date = st.sidebar.date_input("End Date of \"No Outplant Period\"", datetime.now())

    # Ensure valid date range
    if no_outplant_start_date > no_outplant_end_date:
        st.sidebar.error("⚠️ End date of no outplant period must be after start date!")

    # Calculate the difference in days
    no_outplant_start_day = (no_outplant_start_date - selected_datetime).days
    no_outplant_end_day = (no_outplant_end_date - selected_datetime).days

    # Run Forecast and Planning
    if st.button("🚀 Run Forecast and Planning"):
        my_farm = Farm(
            inventory=batches_list,
            prod_tank_capacity=farm_config["PROD_TANK_CAPACITY"],
            prod_tank_num=farm_config["NUM_PROD_TANKS"],
            bs_tank_capacity=farm_config["BS_TANK_CAPACITY"],
            bs_tank_num=farm_config["NUM_BS_TANKS"],
            stage_capacities=farm_config["STAGE_CAPACITIES"],
            production_order=production_order,
            no_outplant_window_start = no_outplant_start_day,
            no_outplant_window_end = no_outplant_end_day
        )

        # Banner message
        banner_message = f"""
        ### No Outplant Period
        - **Start Date:** {no_outplant_start_date} (Day:{no_outplant_start_day} )
        - **End Date:** {no_outplant_end_date} (Day: {no_outplant_end_day})
        """

        # Show the banner at the top of the page
        st.markdown(banner_message)

        # Forecast and Hypothetical Planning
        forecast_result = my_farm.forecast(forecast_days, production_order, sum(production_order.values()))
        final_shortfall_species = {
            spec: forecast_result[1][-1]["species"].get(spec, {}).get("SF",  production_order[spec])
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

        # Weekly Production Changes for Overall Plan    
        st.subheader("Production Plan Weekly Changes")
        unified_changes = pd.DataFrame([total["overall"] for total in unified_result[2]])
        unified_changes["Week"] = unified_changes.index // 7
        weekly_changes = unified_changes.groupby("Week").sum()
        st.bar_chart(weekly_changes[["BS", "MF", "FS", "OP"]])

        # Weekly Production Changes for Overall Plan
        st.subheader("Production Plan Capacity Occupied (Production Tanks)")
        unified_prod_capacity = pd.DataFrame([(farm_config["PROD_TANK_CAPACITY"] * farm_config["NUM_PROD_TANKS"]) - total["prod"] for total in unified_result[3]])
        unified_prod_capacity["Week"] = unified_prod_capacity.index // 7
        weekly_prod_capacity_avail = unified_prod_capacity.groupby("Week").max()
        st.bar_chart(weekly_prod_capacity_avail)

        st.subheader("Production Plan Capacity Occupied (Broodstock Tanks)")
        unified_bs_capacity = pd.DataFrame([(farm_config["BS_TANK_CAPACITY"] * farm_config["NUM_BS_TANKS"]) - total["broodstock"] for total in unified_result[3]])
        unified_bs_capacity["Week"] = unified_bs_capacity.index // 7
        weekly_bs_capacity_avail = unified_bs_capacity.groupby("Week").max()
        st.bar_chart(weekly_bs_capacity_avail)
    
        st.table(unified_totals)

    # Save Unified Plan
    st.subheader("Save Unified Production Plan")
    plan_name = st.text_input("Enter a name for the production plan:", "")
    if st.button("💾 Save Production Plan", key="save_plan_button") and plan_name.strip():
        if "unified_result" in st.session_state:
            result_message = save_production_plan_to_bigquery(credentials, plan_name, st.session_state.unified_result, tenant_option, selected_date)
            st.success(result_message)
        else:
            st.error("No unified result to save. Please run the forecast first.")