import streamlit as st
import pandas as pd
from modules.bigquery_util import current_data
from modules.utils import combine_and_style_compliance_table, generate_mock_compliance_data

def compliance_page():
    st.title("Compliance and Performance Analysis")

    st.sidebar.markdown("Analyze farm performance against production plans.")

    # todo: fetch prod plan fin from this tab
    # todo: get historical fin from date in prod plan fin


    # Mock: Load a locked plan (replace with actual retrieval logic)
    locked_plan = pd.DataFrame({
        "Week": [1, 2, 3],
        "Species": ["PAST", "APAL", "APRO"],
        "BS": [100, 200, 300],
        "MF": [50, 60, 70],
        "FS": [30, 40, 50],
        "OP": [20, 30, 40],
    })

    # Generate compliance data
    compliance_data = generate_mock_compliance_data(locked_plan) # call andrews function

    # Combine and Style Compliance Table
    styled_compliance_table = combine_and_style_compliance_table(locked_plan, compliance_data)

    st.subheader("Weekly Compliance Analysis")
    st.dataframe(styled_compliance_table, height=400)