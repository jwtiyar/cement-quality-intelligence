# Checklist of Excel File Typos & Errors to Fix

If you want to manually clean up your source Excel files, here is the exact checklist of issues to correct:

### 1. The "2014 Template" Copy-Paste Error (Years 2017, 2018, 2019, 2020)
- [ ] **The Issue:** The template from 2014 was copied and reused for the 2017, 2018, 2019, and 2020 files. You changed the data, but forgot to change the actual date cells. The cells in these files literally say things like `2014-01-01` instead of `2017-01-01`.
- [ ] **How to fix:** Go into the Excel files for 2017, 2018, 2019, and 2020 and do a "Find and Replace" on the Date columns to change `2014` to the correct year.

### 2. Missing Full Dates (Years 2013 & 2016)
- [ ] **The Issue:** In the 2013 and 2016 files, the Date columns only contain raw day numbers (1, 2, 3...) instead of actual full dates (like `2013-01-01` or `1/1/2013`). Software systems interpret raw numbers as the year 1900 or 1970.
- [ ] **How to fix:** Change those columns in the 2013 and 2016 files to be proper calendar dates. *(Note: I already created a fixed copy for 2016 called `Daily Report 2016 FIXED.xlsx`, but your original still has the issue).*

### 3. The 2020 Leap Year Bug (Feb 29)
- [ ] **The Issue:** Because 2020 used the copied 2014 template, and 2014 was *not* a leap year, February only had 28 days in the template. When whoever entered the data got to February 29th, 2020, they just typed the raw number `29` into the cell instead of a date. 
- [ ] **How to fix:** In the 2020 Excel file, go to the February section, scroll to the 29th, and change the cell from `29` to `2020-02-29`.

### 4. Inconsistent Column Names Over the Years
- [ ] **The Issue:** The exact spelling of your column headers changes depending on the year. This makes combining data difficult because columns don't align perfectly.
- [ ] **How to fix:** Standardize your headers across all 14 files to match exactly:
  - [ ] **3-Day Strength:** You currently switch between `3 day` and `Cmp.St. Mpa_3 day`.
  - [ ] **2-Day Strength:** Some years test at 2 days instead (`Cmp.St. Mpa_2 day`).
  - [ ] **28-Day Strength:** You currently switch between `28 day` and `28 days`.
  - [ ] **Fineness:** Sometimes there is a space before the parenthesis `Fineness_SSB (cm2/g)` and sometimes there isn't `Fineness_SSB(cm2/g)`.
  - [ ] **Residue:** You switch between `%R,80` and `%R80`.
