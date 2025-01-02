from google.cloud import bigquery
import pandas as pd

def execute_query(query: str) -> pd.DataFrame:
    """
    Execute a given SQL query and return the result as a Pandas DataFrame.
    """
    client = bigquery.Client()
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