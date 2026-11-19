import pandas as pd

from .rules import (
    calculate_available_inventory,
    calculate_projected_shortage,
    calculate_stock_coverage,
    calculate_replenishment_risk
)

REQUIRED_COLUMNS = [
    "sku_id",
    "product_name",
    "current_stock",
    "incoming_stock",
    "expected_demand",
    "unit_cost",
    "moq",
    "order_multiple",
    "lead_time_days",
    "safety_stock",
    "max_stock",
    "priority"
]


def load_inventory_data(file_path):
  

    try:
        data = pd.read_csv(file_path)
        if data.empty:
            raise ValueError("Inventory CSV contains no product rows.")
        print("Inventory data loaded successfully.")
        return data

    except FileNotFoundError:
        raise FileNotFoundError(
            f"Inventory file was not found: {file_path}"
        )
    except ValueError:
        raise

    except Exception as error:
        raise Exception(
            f"An error occurred while loading the inventory file: {error}"
        )


def check_required_columns(data):

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    return True


def check_duplicate_skus(data):
    """Normalize SKU identifiers before enforcing uniqueness."""
    normalized = data["sku_id"].astype("string").str.strip().str.upper()
    if normalized.isna().any() or normalized.eq("").any():
        raise ValueError("SKU IDs cannot be missing or blank.")
    duplicates = normalized[normalized.duplicated(keep=False)]
    if not duplicates.empty:
        raise ValueError(f"Duplicate SKU IDs found after normalization: {sorted(duplicates.unique().tolist())}")
    data["sku_id"] = normalized
    return True


def validate_numeric_fields(data):
   
    integer_columns = [
        "current_stock", "incoming_stock", "expected_demand", "moq",
        "order_multiple", "lead_time_days", "safety_stock", "max_stock", "priority"
    ]
    positive_columns = ["unit_cost", "moq", "order_multiple", "max_stock"]
    for column in integer_columns + ["unit_cost"]:
        numeric = pd.to_numeric(data[column], errors="coerce")
        if numeric.isna().any() or not numeric.map(lambda value: pd.notna(value) and abs(float(value)) != float("inf")).all():
            raise ValueError(f"{column} must contain finite, non-missing numeric values.")
        if column in integer_columns and not numeric.map(lambda value: float(value).is_integer()).all():
            raise ValueError(f"{column} must contain integer values; fractional values are not allowed.")
        data[column] = numeric.astype("int64") if column in integer_columns else numeric.astype(float)
    for column in integer_columns:
        if (data[column] < 0).any():
            raise ValueError(f"{column} cannot contain negative values.")
    for column in positive_columns:
        if (data[column] <= 0).any():
            raise ValueError(f"{column} must contain values greater than zero.")
    return True


def validate_priority(data):
    """Priority must be an integer between 1 and 5."""
    if (~data["priority"].between(1, 5)).any():
        raise ValueError("Priority values must be integers between 1 and 5.")
    return True

def validate_business_rules(data):
   
   
    invalid_safety_stock = (
        data["safety_stock"] > data["max_stock"]
    )

    if invalid_safety_stock.any():
        invalid_skus = data.loc[
            invalid_safety_stock,
            "sku_id"
        ].tolist()

        raise ValueError(
            f"Safety stock exceeds max stock for SKUs: {invalid_skus}"
        )


    return True

def validate_inventory_data(data):
  

    check_required_columns(data)
    check_duplicate_skus(data)
    validate_numeric_fields(data)
    validate_priority(data)
    validate_business_rules(data)

    print("Inventory data validation passed.")

    return True


def add_derived_metrics(data, planning_horizon_days):
 
    data["available_inventory"] = data.apply(
        lambda row: calculate_available_inventory(
            row["current_stock"],
            row["incoming_stock"]
        ),
        axis=1
    )

    data["projected_shortage"] = data.apply(
        lambda row: calculate_projected_shortage(
            row["current_stock"],
            row["incoming_stock"],
            row["expected_demand"],
            row["safety_stock"]
        ),
        axis=1
    )

    data["stock_coverage"] = data.apply(
        lambda row: calculate_stock_coverage(
            row["current_stock"],
            row["incoming_stock"],
            row["expected_demand"]
        ),
        axis=1
    )

    data["replenishment_risk"] = data.apply(
        lambda row: calculate_replenishment_risk(
            row["projected_shortage"],
            row["priority"],
            row["lead_time_days"],
            planning_horizon_days
        ),
        axis=1
    )

    return data

def load_company_config(file_path):
  

    try:
        config_data = pd.read_csv(file_path)

    except FileNotFoundError:
        raise FileNotFoundError(
            f"Company config file was not found: {file_path}"
        )

    except Exception as error:
        raise Exception(
            f"An error occurred while loading company config: {error}"
        )

    if "setting" not in config_data.columns or "value" not in config_data.columns:
        raise ValueError(
            "Company config must contain 'setting' and 'value' columns."
        )

    settings = config_data["setting"].astype("string").str.strip()
    if settings.isna().any() or settings.eq("").any():
        raise ValueError("Company config setting names cannot be blank.")
    normalized = settings.str.lower()
    if normalized.duplicated().any():
        duplicates = sorted(normalized[normalized.duplicated(keep=False)].unique().tolist())
        raise ValueError(f"Duplicate company config settings: {duplicates}")
    config = dict(zip(normalized, config_data["value"]))
    return config

def validate_company_config(config):
  

    required_settings = [
        "purchasing_budget",
        "warehouse_capacity",
        "planning_horizon_days",
        "currency"
    ]

    for setting in required_settings:
        if setting not in config:
            raise ValueError(
                f"Missing company setting: {setting}"
            )

    try:
        purchasing_budget = float(
            config["purchasing_budget"]
        )

        warehouse_capacity_value = float(config["warehouse_capacity"])
        planning_horizon_value = float(config["planning_horizon_days"])
        if not warehouse_capacity_value.is_integer() or not planning_horizon_value.is_integer():
            raise ValueError("Capacity and planning horizon must be integers.")
        warehouse_capacity = int(warehouse_capacity_value)
        planning_horizon_days = int(planning_horizon_value)

    except (TypeError, ValueError, OverflowError):
        raise ValueError("Budget, capacity and planning horizon must be finite numeric values.")

    if not all(pd.notna(x) and abs(x) != float("inf") for x in (purchasing_budget, warehouse_capacity, planning_horizon_days)):
        raise ValueError("Budget, capacity and planning horizon must be finite.")

    if purchasing_budget < 0:
        raise ValueError("Purchasing budget cannot be negative.")

    if warehouse_capacity < 0:
        raise ValueError("Warehouse capacity cannot be negative.")

    if planning_horizon_days <= 0:
        raise ValueError(
            "Planning horizon must be greater than zero."
        )

    if pd.isna(config["currency"]) or not str(config["currency"]).strip():
        raise ValueError(
            "Currency cannot be empty."
        )

    print("Company configuration validation passed.")

    return True

def prepare_project_data(inventory_file, config_file):


  
    inventory = load_inventory_data(inventory_file)


    validate_inventory_data(inventory)

   
    company_config = load_company_config(config_file)
    validate_company_config(company_config)


    inventory = add_derived_metrics(inventory, int(float(company_config["planning_horizon_days"])))

    
    company_config["purchasing_budget"] = float(
        company_config["purchasing_budget"]
    )

    company_config["warehouse_capacity"] = int(
        company_config["warehouse_capacity"]
    )

    company_config["planning_horizon_days"] = int(
        company_config["planning_horizon_days"]
    )

    company_config["currency"] = str(
        company_config["currency"]
    ).strip().upper()

    return inventory, company_config


if __name__ == "__main__":

    inventory_file = "../data/inventory_data.csv"
    config_file = "../data/company_config.csv"

    inventory, company_config = prepare_project_data(
        inventory_file,
        config_file
    )

    print()
    print("Company Configuration:")
    print(company_config)

    print()
    print("Inventory Metrics:")

    print(
        inventory[
            [
                "sku_id",
                "available_inventory",
                "projected_shortage",
                "stock_coverage",
                "replenishment_risk"
            ]
        ]
    )
