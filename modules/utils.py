import pandas as pd
import random

# Helper functions to initialize default parameters
def default_production_order(tenant: str):
    if (tenant == 'saudi'):
        return {'AARA': 30000, 'PVER': 30000, 'ACYT': 10000, 'PNOD': 5000, 'ADIG': 500}
    else:
        return {'PAST': 7000, 'APAL': 6000, 'APRO': 6000, 'PCLI': 3000, 'ACER': 5000}

def default_farm_config(tenant: str):
    if (tenant == 'saudi'):
         return {
        "NUM_PROD_TANKS": 32,
        "TANK_CAPACITY": 2100,
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
    else: 
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

def combine_and_style_compliance_table(plan, actual):

    compare_fields = ['BS','MF','FS','OP']

    actual.rename(columns={col: f"{col}_Actual" for col in compare_fields}, inplace=True)
    plan.rename(columns={col: f"{col}_Plan" for col in compare_fields}, inplace=True)

    combined = pd.merge(actual, plan, on=['Day', 'Species',], how='outer')
    combined = combined[["Type","Date","Species","BS_Actual","BS_Plan","MF_Actual","MF_Plan","FS_Actual","FS_Plan","OP_Actual","OP_Plan"]]

    import pdb
    pdb.set_trace()
    def style_cells(row, col_name):
        if "_Actual" in col_name:
            plan_col = col_name.replace("_Actual", "_Plan")
            plan_value = row[plan_col]
            actual_value = row[col_name]
            if actual_value == 0:
                return ""
            elif actual_value < plan_value:
                return "background-color: #ff9999;"  # Red
            elif actual_value >= plan_value:
                return "background-color: #006400; color: white;"  # Green
        return ""

    styled_table = combined.style.apply(
        lambda row: [
            style_cells(row, col) if "_Actual" in col else "" for col in combined.columns
        ],
        axis=1,
    )
    return styled_table


def create_unified_result(forecast_result, hypothetical_result):
    def merge_lists(list1, list2, is_capacity=False):
        merged = []
        for day_data1, day_data2 in zip(list1, list2):
            if not is_capacity:
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
                merged_day = {
                    "overall": day_data1["overall"] + day_data2["overall"],
                    "stage": {
                        stage: day_data1["stage"].get(stage, 0) + day_data2["stage"].get(stage, 0)
                        for stage in set(day_data1["stage"]) | set(day_data2["stage"])
                    }
                }
            merged.append(merged_day)
        return merged

    unified_inventory = hypothetical_result[0]
    unified_totals = merge_lists(forecast_result[1], hypothetical_result[1])
    unified_changes = merge_lists(forecast_result[2], hypothetical_result[2])
    unified_capacity = hypothetical_result[3]
    return unified_inventory, unified_totals, unified_changes, unified_capacity


def generate_mock_compliance_data(planned: pd.DataFrame) -> pd.DataFrame:
    def mock_value(plan_value):
        if plan_value == 0:
            return 0
        deviation = random.choice([-1, 0, 1])
        return max(0, plan_value + deviation * random.randint(1, 5))

    mock_data = planned.copy()
    for col in ["BS", "MF", "FS", "OP"]:
        if col in planned.columns:
            mock_data[col] = planned[col].apply(mock_value)
    return mock_data