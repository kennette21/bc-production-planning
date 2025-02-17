import streamlit as st
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
from modules.bigquery_util import (
    load_production_plan_from_bigquery,
    load_saved_plan_names,
    load_historical_fin_from_bigquery
)
from modules.utils import style_compliance_table, generate_mock_compliance_data

# Create API client.
credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"]
)
bigQclient = bigquery.Client(credentials=credentials)


def compliance_page():
    st.title("Compliance and Performance Analysis")

    st.sidebar.markdown("Analyze farm performance against production plans.")

    # Fetch available production plans
    plan_names = load_saved_plan_names(bigQclient)

    if not plan_names:
        st.error("No saved production plans found.")
        return

    selected_plan = st.selectbox("Select a Production Plan", plan_names)

    if selected_plan:
        # Load selected production plan
        prod_plan = load_production_plan_from_bigquery(bigQclient,selected_plan)

        # Get the historical FIN from the date of the saved plan
        started_at = prod_plan["StartedAt"].iloc[0]  # Get the date the plan was saved
        started_at_str = started_at.strftime("%Y-%m-%d")
        tenant = prod_plan["tenant"].iloc[0]  # Get the date the plan was saved
        historical_fin = load_historical_fin_from_bigquery(bigQclient, started_at_str, tenant)

        if prod_plan.empty or historical_fin.empty:
            st.error("Error loading data from BigQuery.")
            return

        # Production Plan #
        # Filter for species additions only and relevant fields
        species_additions_plan = prod_plan[prod_plan["Type"] == "species-additions"]
        species_additions_plan['Date'] = species_additions_plan['StartedAt'] + pd.to_timedelta(species_additions_plan['Day'], unit='D')
        species_additions_plan["Date"] = pd.to_datetime(species_additions_plan["Date"]).dt.strftime("%Y-%m-%d")
        species_additions_plan = species_additions_plan.drop(columns=["PlanName", "StartedAt", "SavedAt",  "SF", "tenant"], errors="ignore")

        # Historical FIN #
        # Filter for species additions only and relevant fields
        species_additions_actual = historical_fin[historical_fin["Type"] == "species-additions"]
        species_additions_actual = species_additions_actual.drop(columns=["Type","PlanName", "SF", "tenant"], errors="ignore")
        species_additions_actual["Date"] = pd.to_datetime(species_additions_actual["Date"]).dt.strftime("%Y-%m-%d")

        # Assign a sequential day index per species-tenant group
        # species_additions_actual = species_additions_actual.sort_values(by=['Date','Species'])
        # species_additions_actual['Day'] = species_additions_actual.groupby(['Date','Species']).cumcount()

        # Combine plan and actual tables
        compare_fields = ['BS','MF','FS','OP']
        species_additions_actual.rename(columns={col: f"{col}_Actual" for col in compare_fields}, inplace=True)
        species_additions_plan.rename(columns={col: f"{col}_Plan" for col in compare_fields}, inplace=True)

        
        compliance_table = pd.merge(species_additions_actual, species_additions_plan, on=['Date', 'Species',], how='outer')
        compliance_table = compliance_table[["Type","Date","Species","BS_Actual","BS_Plan","MF_Actual","MF_Plan","FS_Actual","FS_Plan","OP_Actual","OP_Plan"]]

        # Fill NaN values with 0 before converting to integers
        compliance_table = compliance_table.fillna(0)

        # Drop rows where all 8 fields are empty or NaN
        compliance_table = compliance_table[
            ~compliance_table[["BS_Actual", "BS_Plan", "MF_Actual", "MF_Plan", "FS_Actual", "FS_Plan", "OP_Actual", "OP_Plan"]]
            .eq(0).all(axis=1)
]
        # Ensure numeric columns are integers
        numeric_columns = compliance_table.select_dtypes(include=["float", "int"]).columns
        compliance_table[numeric_columns] = compliance_table[numeric_columns].astype(int)

        # Sort Day and Species in ascending  order
        compliance_table = compliance_table.sort_values(by=["Date","Species"], ascending=True)

        # Style compliance table(styled_compliance_table, height=400)
        styled_compliance_table = style_compliance_table(compliance_table)

        st.subheader("Weekly Compliance Analysis")
        st.dataframe(styled_compliance_table, height=600, width= 200)
