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

def save_production_plan_to_bigquery(plan_name, unified_result, tenant: str, selected_date: str):
    """
    Save the unified production plan (unified_result) to BigQuery in a unified table.

    Parameters:
        plan_name (str): Name of the production plan.
        unified_result (tuple): The unified production plan result, containing rolling totals and changes.

    Returns:
        str: Success message or error message.
    """
    # Extract daily totals
    daily_totals = pd.DataFrame([
        {"Day": day, "Type": "totals", "Species": None, "tenant": tenant, **total["overall"]}
        for day, total in enumerate(unified_result[1])
    ])

    # Extract daily additions
    daily_additions = pd.DataFrame([
        {"Day": day, "Type": "additions", "Species": None, "tenant": tenant, **changes["overall"]}
        for day, changes in enumerate(unified_result[2])
    ])

    # Extract species-level totals
    species_totals = pd.DataFrame([
        {"Day": day, "Type": "species-totals", "Species": species, "tenant": tenant, **data}
        for day, total in enumerate(unified_result[1])
        for species, data in total["species"].items()
    ])

    # Extract species-level totals
    species_additions = pd.DataFrame([
        {"Day": day, "Type": "species-additions", "Species": species, "tenant": tenant, **data}
        for day, total in enumerate(unified_result[2])
        for species, data in total["species"].items()
    ])

    # Combine all data
    combined_data = pd.concat([daily_totals, daily_additions, species_totals, species_additions], ignore_index=True)

    # Add metadata
    combined_data["PlanName"] = plan_name
    combined_data["SavedAt"] = pd.Timestamp.now()
    combined_data["StartedAt"] = pd.Timestamp(selected_date)

    # Save to BigQuery
    table_id = "brain-coral.prod_planning_mvp.production_plans"
    try:
        combined_data.to_gbq(table_id, if_exists="append", credentials=credentials)
        return f"Production plan '{plan_name}' saved successfully!"
    except Exception as e:
        return f"Error saving production plan '{plan_name}': {e}"
    

def load_saved_plan_names():
    """
    Fetch all unique plan names from the production plans table.
    """
    query = """
    SELECT DISTINCT PlanName FROM `brain-coral.prod_planning_mvp.production_plans`
    """
    return client.query(query).to_dataframe()["PlanName"].tolist()

def load_production_plan_from_bigquery(plan_name: str) -> pd.DataFrame:
    """
    Fetch a locked production plan from BigQuery based on its name.
    """
    query = f"""
        SELECT * 
        FROM `brain-coral.prod_planning_mvp.production_plans`
        WHERE PlanName = '{plan_name}'
    """
    return execute_query(query)

def load_historical_fin_from_bigquery(saved_date: str, tenant: str) -> pd.DataFrame:
    """
    Fetch historical FIN (farm inventory numbers) from BigQuery based on the saved production plan date.
    """
    query = f"""
    SELECT * 
    FROM 
        `brain-coral.prod_planning_mvp.daily_totals_all` 
    WHERE 
        tenant = CONCAT("tenants/","{tenant}") AND 
        Date >= "{saved_date}";
    """
    df = execute_query(query)

    # Check plan data quality
    assert df[['Type','Date','Species','tenant']].notna().all().all()
    assert len(df[['Type','Date','Species','tenant']].drop_duplicates()) == len(df)

    # Fix date
    df["new_Date"] = pd.to_datetime(df['Date'], format='%Y-%m-%d', errors='coerce')

    # Drop the original 'Date' column and rename 'new_Date' to 'Date'
    df.drop(columns=["Date"], errors="ignore", inplace=True)
    df.rename(columns={"new_Date": "Date"}, inplace=True)
    return df

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

def current_data(tenant: str) -> pd.DataFrame:
    """
    Pull the current data at the farm so that it can be piped into the model.
    Includes outplants in December 2024 for demonstration purposes.
    """
    QUERY = f"""
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
            Tenant = '{tenant}' AND
            (CurrentLocationType = 'ex situ') AND 
            CurrentLocationName NOT IN ('Reef Tank', 'Happy Tank', 'Spawning System', 'Tree Tank')
    """
    return execute_query(QUERY)

def historical_data(date: str, tenant: str) -> pd.DataFrame:
    """
    Pull the  data at the farm from a particular date. that it can be piped into the model.
    """

    # Base query fragment to avoid redundancy
    def get_query(table_name: str, include_fs_plug_count: bool = False) -> str:
        columns = f"""
            batch_doc_id AS BatchDocID,
            batch_id AS BatchID,
            LEFT(batch_id, 4) AS Species,
            batch_alteration AS Alteration,
            NULL AS SurfaceArea,
            current_batch_quantity AS CurrentQuantity,
            current_location_type AS CurrentLocationType,
            {'current_batch_fs_plug_count AS CurrentFSPlugCount,' if include_fs_plug_count else 'NULL AS CurrentFSPlugCount,'}
            DATE(started_at) AS StartDate,
            outplant_date AS OutplantDate,
            NULL AS StdBroodstockAcclimationDays,
            NULL AS StdBroodstockQuarantineDays,
            NULL AS StdBroodstockMortalityPct,
            NULL AS StdBroodstockSAConversionRatio,
            NULL AS StdMicrofragCycleDays,
            NULL AS StdMicrofragMortalityPct,
            NULL AS StdFusionStructureCycleDays,
            NULL AS StdFusionStructureMortalityPct
        """

        return f"""
        SELECT {columns}
        FROM `{table_name}`
        WHERE 
            is_last_row_batch_day = True AND
            tenant = 'tenants/{tenant}' AND
            transition_date = '{date}' AND
            current_location_type = 'ex situ' AND 
            current_location NOT IN ('Reef Tank', 'Happy Tank', 'Spawning System', 'Tree Tank')
        """

    # Combine all UNION queries
    QUERY = f"""
    {get_query('brain-coral.api.daily_batch_mf')}
    UNION ALL
    {get_query('brain-coral.api.daily_batch_fs', include_fs_plug_count=True)}
    UNION ALL
    {get_query('brain-coral.api.daily_batch_broodstock')}
    """

    # Execute the query and return the resulting DataFrame
    df = execute_query(QUERY)    
    return df