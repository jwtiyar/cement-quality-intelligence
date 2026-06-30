import os
import pandas as pd
from datetime import datetime, timedelta

def get_days_in_month(year, month):
    if month == 12: return 31
    return (datetime(year, month+1, 1) - timedelta(days=1)).day

def parse_sheet_block(df, year, sheet_name, c_type, start_row):
    records = []
    header_row1 = start_row + 5
    header_row2 = start_row + 6
    data_start = start_row + 7
    
    if data_start >= len(df): return records
    
    sio2_cols = []
    for c in df.columns:
        h1 = str(df.at[header_row1, c]).strip()
        h2 = str(df.at[header_row2, c]).strip()
        if h1 == 'SiO2' or h2 == 'SiO2':
            sio2_cols.append(c)
            
    if len(sio2_cols) == 0:
        print(f"Warning: {c_type} in {year} has 0 SiO2 columns. Skipping.")
        return records

    for month_idx, sio2_c in enumerate(sio2_cols):
        month = month_idx + 1
        days_in_m = get_days_in_month(year, month)
        
        # Build header map for this month
        month_headers = {}
        # Search window around SiO2
        start_col = max(0, sio2_c - 3)
        end_col = min(len(df.columns), sio2_c + 25)
        
        for c in range(start_col, end_col):
            h1 = str(df.at[header_row1, c]).strip()
            h2 = str(df.at[header_row2, c]).strip()
            h = h2 if h2 != 'nan' and h2 else h1
            if h != 'nan' and h:
                # If there are duplicate headers in the same month block, keep the first one
                if h not in month_headers:
                    month_headers[h] = c
                    
        for day in range(1, days_in_m + 1):
            row_idx = data_start + day - 1
            if row_idx >= len(df): break
            
            # Check if there is any data
            has_data = False
            record = {
                'Year': year,
                'Month_Num': month,
                'Cement_Type': c_type,
                'Date': f"{year}-{month:02d}-{day:02d}"
            }
            
            for h_name, c_idx in month_headers.items():
                val = df.at[row_idx, c_idx]
                if pd.notna(val) and str(val).strip() != '':
                    has_data = True
                    # Prevent overwriting core identifiers
                    if h_name in ['Date', 'Year', 'Month_Num', 'Cement_Type']:
                        record[f'Excel_{h_name}'] = val
                    else:
                        record[h_name] = val
                    
            if has_data:
                records.append(record)
                
    return records

def extract_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    years = range(2013, 2050)
    cement_types = ['OPC', 'SRC', 'SBC']
    
    all_records = []
    
    for year in years:
        year_dir = os.path.join(os.path.dirname(base_dir), str(year))
        if not os.path.exists(year_dir): continue
        print(f"Extracting Year {year}...")
        
        excel_file = None
        for f in os.listdir(year_dir):
            if f.endswith('.xlsx') and not f.startswith('~$'):
                if year == 2016 and "FIXED" in f:
                    excel_file = f
                    break
                elif year != 2016:
                    excel_file = f
                    break
                    
        if not excel_file: continue
        file_path = os.path.join(year_dir, excel_file)
        
        try:
            xl = pd.ExcelFile(file_path)
            # strictly follow instruction: ONLY process 'Daily Report' or actual cement tabs
            if 'Daily Report' in xl.sheet_names:
                sheets_to_process = ['Daily Report']
            else:
                sheets_to_process = [s for s in xl.sheet_names if s in cement_types]
            
            for sheet in sheets_to_process:
                df = pd.read_excel(file_path, sheet_name=sheet, header=None)
                
                blocks = {}
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
                    recs = parse_sheet_block(df, year, sheet, c_type, start_row)
                    all_records.extend(recs)
                    
        except Exception as e:
            print(f"Error in {year}: {e}")

    print("Merging extracted fragments...")
    if not all_records:
        print("No records found!")
        return
        
    final_df = pd.DataFrame(all_records)
    
    # Drop rows that don't have complete chemical analysis
    chem_cols = ['SiO2', 'Al2O3', 'Fe2O3', 'CaO']
    for col in chem_cols:
        if col in final_df.columns:
            final_df = final_df.dropna(subset=[col])
            final_df = final_df[final_df[col].astype(str).str.strip() != '']
        
    out_path = os.path.join(base_dir, "ALL_CEMENT_DATA.csv")
    final_df.to_csv(out_path, index=False)
    print(f"Extraction complete! Saved to {out_path} with {len(final_df)} strict records.")

if __name__ == '__main__':
    extract_data()
