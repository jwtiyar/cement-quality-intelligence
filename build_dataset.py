"""Extract and consolidate cement plant laboratory workbooks into a strict dataset.

Includes workbook/sheet/column provenance and deletion validation to protect data
integrity during refresh.
"""

from __future__ import annotations

import calendar
import os
from typing import Any
import pandas as pd


class UnexplainedDataLossError(RuntimeError):
    """Raised when a candidate scan would silently delete existing historical records."""


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
    found_years: list[int] = []

    for year in years:
        year_dir = os.path.join(parent_dir, str(year))
        if not os.path.exists(year_dir):
            continue

        excel_file = None
        for f in os.listdir(year_dir):
            if f.endswith(".xlsx") and not f.startswith("~$"):
                if year == 2016 and "FIXED" in f:
                    excel_file = f
                    break
                elif year != 2016:
                    excel_file = f
                    break

        if not excel_file:
            continue
        found_years.append(year)
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
        if col in final_df.columns:
            final_df = final_df.dropna(subset=[col])
            final_df = final_df[final_df[col].astype(str).str.strip() != ""]

    # Validation against existing dataset: detect unexplained data loss
    ref_csv = existing_csv_path or os.path.join(app_dir, "ALL_CEMENT_DATA.csv")
    if os.path.exists(ref_csv):
        try:
            old_df = pd.read_csv(ref_csv)
            if not old_df.empty and "Date" in old_df.columns and "Cement_Type" in old_df.columns:
                old_keys = set(old_df["Date"].astype(str) + "_" + old_df["Cement_Type"].astype(str))
                new_keys = set(final_df["Date"].astype(str) + "_" + final_df["Cement_Type"].astype(str))
                missing_keys = old_keys - new_keys
                if missing_keys and not allow_deletions:
                    raise UnexplainedDataLossError(
                        f"Dataset refresh aborted: {len(missing_keys)} previously existing sample records would be lost. "
                        f"Scanned years: {found_years}. Set allow_deletions=True to explicitly confirm removal. "
                        f"Example missing keys: {list(missing_keys)[:5]}"
                    )
        except UnexplainedDataLossError:
            raise
        except Exception as e:
            # If reading old CSV failed, log warning but don't crash
            print(f"Warning: could not inspect existing CSV for comparison: {e}")

    out_path = target_path or os.path.join(app_dir, "ALL_CEMENT_DATA.csv")
    tmp_path = out_path + ".tmp"
    final_df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, out_path)
    print(f"Extraction complete! Saved to {out_path} with {len(final_df)} validated records.")
    return final_df


if __name__ == "__main__":
    extract_data()
