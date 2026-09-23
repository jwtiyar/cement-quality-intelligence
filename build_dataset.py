"""Extract and consolidate cement plant laboratory workbooks into a strict dataset.

Includes workbook/sheet/column provenance and deletion validation to protect data
integrity during refresh.
"""

from __future__ import annotations

import calendar
from collections import Counter
import os
from typing import Any
import pandas as pd


class UnexplainedDataLossError(RuntimeError):
    """Raised when a candidate scan would silently delete existing historical records."""


def _historical_changes(old_df: pd.DataFrame, new_df: pd.DataFrame) -> list[str]:
    """Find missing records or previously recorded measurements in a new scan."""
    key_cols = ["Date", "Cement_Type"]
    old_keys = Counter(old_df[key_cols].astype(str).itertuples(index=False, name=None))
    new_keys = Counter(new_df[key_cols].astype(str).itertuples(index=False, name=None))
    missing = old_keys - new_keys
    problems = [f"{sum(missing.values())} missing records"] if missing else []

    metadata = {"Date", "Cement_Type", "Year", "Month_Num", "Excel_Date", "Source_File", "Source_Sheet", "Source_Column_28D"}
    for column in old_df.columns:
        if column in metadata or column.startswith("Excel_") or column.startswith("Source_"):
            continue
        old_values = pd.to_numeric(old_df[column], errors="coerce")
        if not old_values.notna().any():
            continue
        new_values = (
            pd.to_numeric(new_df[column], errors="coerce")
            if column in new_df else pd.Series(float("nan"), index=new_df.index)
        )

        def values(frame: pd.DataFrame, numeric: pd.Series) -> Counter:
            rows = frame.loc[numeric.notna(), key_cols].astype(str)
            return Counter(
                (date, cement_type, format(value, ".10g"))
                for (date, cement_type), value in zip(
                    rows.itertuples(index=False, name=None), numeric[numeric.notna()]
                )
            )

        lost_values = values(old_df, old_values) - values(new_df, new_values)
        if lost_values:
            problems.append(f"{column}: {sum(lost_values.values())} changed or missing values")
    return problems


def get_days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def parse_sheet_block(
    df: pd.DataFrame,
    year: int,
    sheet_name: str,
    c_type: str,
    start_row: int,
    source_file: str = "unknown",
) -> list[dict[str, Any]]:
    records = []
    header_row1 = start_row + 5
    header_row2 = start_row + 6
    data_start = start_row + 7

    if data_start >= len(df):
        return records

    sio2_cols = []
    for c in df.columns:
        h1 = str(df.at[header_row1, c]).strip()
        h2 = str(df.at[header_row2, c]).strip()
        if h1 == "SiO2" or h2 == "SiO2":
            sio2_cols.append(c)

    if len(sio2_cols) == 0:
        return records

    for month_idx, sio2_c in enumerate(sio2_cols):
        month = month_idx + 1
        days_in_m = get_days_in_month(year, month)

        month_headers: dict[str, int] = {}
        start_col = max(0, sio2_c - 3)
        end_col = min(len(df.columns), sio2_c + 25)

        for c in range(start_col, end_col):
            h1 = str(df.at[header_row1, c]).strip()
            h2 = str(df.at[header_row2, c]).strip()
            h = h2 if h2 != "nan" and h2 else h1
            if h != "nan" and h:
                if h not in month_headers:
                    month_headers[h] = c

        for day in range(1, days_in_m + 1):
            row_idx = data_start + day - 1
            if row_idx >= len(df):
                break

            has_data = False
            record: dict[str, Any] = {
                "Year": year,
                "Month_Num": month,
                "Cement_Type": c_type,
                "Date": f"{year}-{month:02d}-{day:02d}",
                "Source_File": source_file,
                "Source_Sheet": sheet_name,
            }

            for h_name, c_idx in month_headers.items():
                val = df.at[row_idx, c_idx]
                if pd.notna(val) and str(val).strip() != "":
                    has_data = True
                    if h_name in ["Date", "Year", "Month_Num", "Cement_Type"]:
                        record[f"Excel_{h_name}"] = val
                    else:
                        record[h_name] = val
                    if "28" in h_name:
                        record["Source_Column_28D"] = h_name

            if has_data:
                records.append(record)

    return records


def extract_data(
    base_dir: str | None = None,
    target_path: str | None = None,
    allow_deletions: bool = False,
    existing_csv_path: str | None = None,
) -> pd.DataFrame:
    """
    Extract plant records across available year folders into an in-memory DataFrame.
    Validates completeness against the existing dataset before publishing.
    """
    app_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(app_dir)
    years = range(2013, 2050)
    cement_types = ["OPC", "SRC", "SBC"]

    all_records: list[dict[str, Any]] = []
    errors: list[str] = []

    for year in years:
        year_dir = os.path.join(parent_dir, str(year))
        if not os.path.exists(year_dir):
            continue

        workbooks = sorted(f for f in os.listdir(year_dir) if f.endswith(".xlsx") and not f.startswith("~$"))
        if not workbooks:
            continue
        if year == 2016:
            workbooks = [f for f in workbooks if "FIXED" in f.upper()]
            if not workbooks:
                raise RuntimeError("2016 FIXED workbook is missing; existing CSV was preserved.")
        if len(workbooks) != 1:
            raise RuntimeError(f"Multiple workbooks found for {year}; choose one before refreshing: {workbooks}")
        excel_file = workbooks[0]
        file_path = os.path.join(year_dir, excel_file)

        try:
            xl = pd.ExcelFile(file_path)
            if "Daily Report" in xl.sheet_names:
                sheets_to_process = ["Daily Report"]
            else:
                sheets_to_process = [s for s in xl.sheet_names if s in cement_types]

            for sheet in sheets_to_process:
                df = pd.read_excel(file_path, sheet_name=sheet, header=None)

                blocks: dict[str, int] = {}
                for i, row in df.iterrows():
                    for cell_val in row:
                        if pd.isna(cell_val):
                            continue
                        val_str = str(cell_val).strip().upper()
                        for ct in cement_types:
                            if f"({ct})" in val_str or ct == val_str:
                                if ct not in blocks:
                                    blocks[ct] = i

                if not blocks and sheet in cement_types:
                    blocks[sheet] = 0

                for c_type, start_row in blocks.items():
                    recs = parse_sheet_block(
                        df, year, sheet, c_type, start_row, source_file=excel_file
                    )
                    all_records.extend(recs)

        except Exception as e:
            errors.append(f"{year}: {e}")

    if errors:
        raise RuntimeError(
            "Dataset refresh aborted; existing CSV was preserved. "
            f"Workbook errors: {'; '.join(errors)}"
        )

    if not all_records:
        raise RuntimeError("No records found across scanned workbooks.")

    final_df = pd.DataFrame(all_records)

    # Clean rows lacking core chemical oxides
    chem_cols = ["SiO2", "Al2O3", "Fe2O3", "CaO"]
    for col in chem_cols:
        if col not in final_df.columns:
            raise RuntimeError(f"Dataset refresh aborted: required column {col} is missing.")
        final_df = final_df.dropna(subset=[col])
        final_df = final_df[final_df[col].astype(str).str.strip() != ""]
    if final_df.empty:
        raise RuntimeError("Dataset refresh aborted: no records have the required oxide measurements.")

    # Validation against existing dataset: detect unexplained data loss
    ref_csv = existing_csv_path or os.path.join(app_dir, "ALL_CEMENT_DATA.csv")
    if os.path.exists(ref_csv):
        try:
            old_df = pd.read_csv(ref_csv)
            if old_df.empty or not {"Date", "Cement_Type"}.issubset(old_df.columns):
                raise ValueError("active dataset is empty or lacks Date/Cement_Type columns")
            changes = _historical_changes(old_df, final_df)
            if changes and not allow_deletions:
                raise UnexplainedDataLossError(
                    "Dataset refresh aborted; existing records or measurements changed. "
                    f"Review the source workbooks before overriding with allow_deletions=True. Details: {'; '.join(changes[:8])}"
                )
        except UnexplainedDataLossError:
            raise
        except Exception as e:
            raise RuntimeError(f"Dataset refresh aborted: could not validate existing CSV: {e}") from e

    out_path = target_path or os.path.join(app_dir, "ALL_CEMENT_DATA.csv")
    tmp_path = out_path + ".tmp"
    final_df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, out_path)
    print(f"Extraction complete! Saved to {out_path} with {len(final_df)} validated records.")
    return final_df


if __name__ == "__main__":
    extract_data()
