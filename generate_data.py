import pandas as pd
import numpy as np
from datetime import datetime, timedelta

start_date = datetime(2025, 7, 1)
days = 180

data = []

for i in range(days):
    date = start_date + timedelta(days=i)

    # SoftDrink - peak ช่วงหน้าร้อน (เดือน 12-4)
    if date.month in [12,1,2,3,4]:
        softdrink_qty = np.random.randint(50, 80)
    else:
        softdrink_qty = np.random.randint(20, 40)

    # Umbrella - peak ช่วงหน้าฝน (เดือน 7-10)
    if date.month in [7,8,9,10]:
        umbrella_qty = np.random.randint(30, 60)
    else:
        umbrella_qty = np.random.randint(5, 15)

    data.append([date, "SoftDrink", softdrink_qty, softdrink_qty*30])
    data.append([date, "Umbrella", umbrella_qty, umbrella_qty*50])

df = pd.DataFrame(data, columns=["sale_date","product_name","quantity","total_price"])
df.to_csv("sales_data.csv", index=False)

print("CSV generated!")