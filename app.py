# app.py
import streamlit as st #
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="Risk Dashboard@", layout="wide")

st.title("🦟 Food Spoilage & Cockroach Risk Dashboard")

uploaded_file = st.file_uploader("Upload your weather Excel file", type=["xlsx"])


def cockroach_risk(temp, hum):
    # Temperature score
    if temp < 15:
        t = 0
    elif temp < 20:
        t = 0.2
    elif temp < 25:
        t = 0.5
    elif temp < 30:
        t = 0.9
    elif temp < 35:
        t = 1.0
    else:
        t = 0.6

    # Humidity score
    if hum < 40:
        h = 0.2
    elif hum < 60:
        h = 0.5
    elif hum < 70:
        h = 0.8
    else:
        h = 1.0

    return round((t * 0.6 + h * 0.4), 2)


def spoilage_risk(temp, hum):
    # Temperature score
    if temp < 4:
        t = 0
    elif temp < 10:
        t = 0.2
    elif temp < 20:
        t = 0.4
    elif temp < 45:
        t = 1.0
    elif temp < 60:
        t = 0.7
    else:
        t = 0.1

    # Humidity score
    if hum < 40:
        h = 0.3
    elif hum < 60:
        h = 0.6
    elif hum < 80:
        h = 0.9
    else:
        h = 1.0

    return round((t * 0.7 + h * 0.3), 2)


def level(x):
    if x >= 0.8:
        return "High"
    elif x >= 0.5:
        return "Medium"
    else:
        return "Low"


if uploaded_file:
    df = pd.read_excel(uploaded_file)

    # 컬럼 자동 탐지
    temp_col = [c for c in df.columns if "temp" in c.lower() or "기온" in c][0]
    hum_col = [c for c in df.columns if "hum" in c.lower() or "습도" in c][0]

    df["Cockroach_Risk"] = df.apply(lambda x: cockroach_risk(x[temp_col], x[hum_col]), axis=1)
    df["Food_Spoilage_Risk"] = df.apply(lambda x: spoilage_risk(x[temp_col], x[hum_col]), axis=1)

    df["Cockroach_Level"] = df["Cockroach_Risk"].apply(level)
    df["Spoilage_Level"] = df["Food_Spoilage_Risk"].apply(level)

    st.subheader("📊 Data Preview")
    st.dataframe(df)

    # 오늘 데이터 강조
    today = datetime.today().date()

    if "date" in [c.lower() for c in df.columns]:
        date_col = [c for c in df.columns if "date" in c.lower()][0]
        df[date_col] = pd.to_datetime(df[date_col]).dt.date
        today_df = df[df[date_col] == today]

        if not today_df.empty:
            st.subheader("🚨 Today Risk Alert")
            c_risk = today_df.iloc[0]["Cockroach_Risk"]
            f_risk = today_df.iloc[0]["Food_Spoilage_Risk"]

            st.metric("Cockroach Risk", c_risk)
            st.metric("Food Spoilage Risk", f_risk)

    st.subheader("📈 Risk Trend")
    st.line_chart(df[["Cockroach_Risk", "Food_Spoilage_Risk"]])

else:
    st.info("엑셀 파일을 업로드해주세요")



