import streamlit as st
import pandas as pd
from modules.bigquery_util import (
    load_production_plan_from_bigquery,
    load_saved_plan_names,
    load_historical_fin_from_bigquery
)
from modules.utils import combine_and_style_compliance_table, generate_mock_compliance_data

def compliance_page():
    st.title("Compliance and Performance Analysis")

    st.sidebar.markdown("Analyze farm performance against production plans.")

    # todo: fetch prod plan fin from this tab
    # todo: get historical fin from date in prod plan fin

    # Fetch available production plans
    plan_names = load_saved_plan_names()

    if not plan_names:
        st.error("No saved production plans found.")
        return

    selected_plan = st.selectbox("Select a Production Plan", plan_names)

    if selected_plan:
        # Load selected production plan
        prod_plan = load_production_plan_from_bigquery(selected_plan)

        # Get the historical FIN from the date of the saved plan
        started_at = prod_plan["StartedAt"].iloc[0]  # Get the date the plan was saved
        started_at_str = started_at.strftime("%Y-%m-%d")
        tenant = prod_plan["tenant"].iloc[0]  # Get the date the plan was saved
        historical_fin = load_historical_fin_from_bigquery(started_at_str, tenant)

        if prod_plan.empty or historical_fin.empty:
            st.error("Error loading data from BigQuery.")
            return

        # Filter for species additions only
        species_additions_plan = prod_plan[prod_plan["Type"] == "species-additions"]
        species_additions_plan = species_additions_plan.drop(columns=["PlanName", "SavedAt", "SF", "tenant"], errors="ignore")
        species_additions_plan = species_additions_plan.sort_values(by=["Day"], ascending=True)

        # Drop unnecessary columns from historical_fin
        species_additions_actual = historical_fin[historical_fin["Type"] == "species-additions"]
        species_additions_actual = species_additions_actual.drop(columns=["Type","PlanName", "SF", "tenant"], errors="ignore")

        # Assign a sequential day index per species-tenant group
        species_additions_actual = species_additions_actual.sort_values(by=['Date','Species'])
        species_additions_actual['Day'] = species_additions_actual.groupby(['Date','Species']).cumcount()

        # Fill NaN values with 0 before converting to integers
        species_additions_plan = species_additions_plan.fillna(0)
        species_additions_actual = species_additions_actual.fillna(0)

        # Ensure numeric columns are integers
        numeric_columns = species_additions_plan.select_dtypes(include=["float", "int"]).columns
        species_additions_plan[numeric_columns] = species_additions_plan[numeric_columns].astype(int)

        numeric_columns_hist = species_additions_actual.select_dtypes(include=["float", "int"]).columns
        species_additions_actual[numeric_columns_hist] = species_additions_actual[numeric_columns_hist].astype(int)

        # Sort both tables by Day in ascending order
        species_additions_plan = species_additions_plan.sort_values(by=["Day"], ascending=True)
        species_additions_actual = species_additions_actual.sort_values(by=["Day"], ascending=True)

        # Combine and style compliance table(styled_compliance_table, height=400)
        styled_compliance_table = combine_and_style_compliance_table(species_additions_plan, species_additions_actual)


        st.subheader("Weekly Compliance Analysis")
        st.dataframe(styled_compliance_table, height=400)
