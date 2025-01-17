from google.cloud import bigquery
import streamlit as st
from google.oauth2 import service_account
import pandas as pd
from modules.farm import Batch
from datetime import date

# Create API client.
credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"]
)
client = bigquery.Client(credentials=credentials)

# Default values for Batch initialization (align with your app's config)
DEFAULT_BS_QUANTITY = 100
MF_CYCLE_DAYS = 30
FS_CYCLE_DAYS = 90
BS_MORTALITY_STD = 0.05
MF_MORTALITY_STD = 0.1
FS_MORTALITY_STD = 0.05

def save_production_plan_to_bigquery(plan_name, plan_data):
    plan_data["PlanName"] = plan_name
    plan_data["SavedAt"] = pd.Timestamp.now()
    plan_data.to_gbq("brain-coral.prod_planning_mvp.locked_plans", if_exists="append")

def load_production_plan_from_bigquery(plan_name):
    query = f"""
        SELECT *
        FROM `your_dataset.production_plans`
        WHERE PlanName = '{plan_name}'
    """
    return execute_query(query)

def load_saved_plan_names():
    """
    Get a list of all locked plan IDs.
    """
    client = bigquery.Client()
    query = """
    SELECT PlanName FROM `brain-coral.prod_planning_mvp.locked_plans`
    """
    return client.query(query).to_dataframe()["plan_id"].tolist()

def row_to_batch(row: dict) -> Batch:
    """
    Convert a row from BigQuery into a Batch object.
    """
    today = date.today().toordinal()
    start_date = pd.to_datetime(row["StartDate"]).toordinal() - today

    # Normalize missing values
    def safe_get(value, default):
        return default if pd.isna(value) or value is None else value

    # Determine stage and quantity based on alteration logic
    if row['Alteration'] == "broodstock":
        stage = "BS"
        if pd.isna(row['SurfaceArea']) or pd.isna(row['StdBroodstockSAConversionRatio']):
            quantity = DEFAULT_BS_QUANTITY
        else:
            quantity = DEFAULT_BS_QUANTITY
            # Uncomment and adjust if SurfaceArea-based calculation is required
            # quantity = round(int(row['SurfaceArea']) / row['StdBroodstockSAConversionRatio'])
    elif row['Alteration'] == "mf":
        stage = "MF"
        quantity = row['CurrentQuantity']
    elif (row['Alteration'] == "fs") & (row['CurrentLocationType'] == "ex situ"):
        stage = 'FS'
        quantity = row['CurrentFSPlugCount']
    elif (row['Alteration'] == "mf") & (row['OutplantDate'] is not None):
        stage = "OP"
        quantity = row['CurrentQuantity']
    elif (row['Alteration'] == "fs") & (row['OutplantDate'] is not None):
        stage = "OP"
        quantity = row['CurrentFSPlugCount']
    else:
        raise ValueError(f"Error: Unable to assign a stage for Alteration = {row['BatchID']}. Please verify the input.")

    # Initialize and return Batch object
    new_batch = Batch(
        batch_id=row["BatchID"],
        species=row["Species"],
        quantity=int(safe_get(quantity, DEFAULT_BS_QUANTITY)),
        stage=stage,
        start_date=start_date,
        bs_cycle_days=int(safe_get(row["StdBroodstockAcclimationDays"], 14))
                      + int(safe_get(row["StdBroodstockQuarantineDays"], 14)),
        mf_cycle_days=int(safe_get(row["StdMicrofragCycleDays"], MF_CYCLE_DAYS)),
        fs_cycle_days=int(safe_get(row["StdFusionStructureCycleDays"], FS_CYCLE_DAYS)),
        bs_mortality_std=float(safe_get(row["StdBroodstockMortalityPct"], BS_MORTALITY_STD)),
        mf_mortality_std=float(safe_get(row["StdMicrofragMortalityPct"], MF_MORTALITY_STD)),
        fs_mortality_std=float(safe_get(row["StdFusionStructureMortalityPct"], FS_MORTALITY_STD)),
    )

    return new_batch

def execute_query(query: str) -> pd.DataFrame:
    """
    Execute a given SQL query and return the result as a Pandas DataFrame.
    """
    query_job = client.query(query)  # API request
    results = query_job.result()  # Waits for query to finish
    return results.to_dataframe()

def current_data() -> pd.DataFrame:
    """
    Pull the current data at the farm so that it can be piped into the model.
    Includes outplants in December 2024 for demonstration purposes.
    """
    QUERY = """
        SELECT
            BatchDocID,
            BatchID,
            LEFT(BatchID, 4) AS Species,
            Alteration,
            CASE
                WHEN SurfaceArea = 0 THEN NULL
                ELSE SurfaceArea
            END AS SurfaceArea,
            CurrentQuantity,
            CurrentLocationType,
            CurrentFSPlugCount,
            DATE(StartedAtTimestamp) AS StartDate,
            OutplantDate,
            StdBroodstockAcclimationDays,
            StdBroodstockQuarantineDays,
            StdBroodstockMortalityPct,
            StdBroodstockSAConversionRatio,
            StdMicrofragCycleDays,
            StdMicrofragMortalityPct,
            StdFusionStructureCycleDays,
            StdFusionStructureMortalityPct
        FROM `brain-coral.api.batches_clean` 
        WHERE 
            CurrentQuantity > 0 AND
            Tenant = 'freeport' AND
            (CurrentLocationType = 'ex situ' OR OutplantDate > '2024-12-01') AND 
            CurrentLocationName NOT IN ('Reef Tank', 'Happy Tank', 'Spawning System', 'Tree Tank')
    """
    return execute_query(QUERY)