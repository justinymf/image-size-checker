import streamlit as st
import pandas as pd
import json
import requests
from concurrent.futures import ThreadPoolExecutor
import time

# 設定頁面資訊
st.set_page_config(page_title="Image Checker Pro", layout="wide", page_icon="🖼️")

st.title("🖼️ 圖片網址效能與狀態檢查工具")

# --- 通用檢查函數 ---
def check_image_size(url):
    """檢查單張圖片的大小與狀態"""
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return {"url": url, "status": "⚠️ Invalid URL", "size_kb": 0, "error": "Malformed URL"}
    try:
        # 使用 HEAD 請求節省頻寬，並設定 5 秒超時
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            size_bytes = int(response.headers.get('Content-Length', 0))
            size_kb = round(size_bytes / 1024, 2)
            return {"url": url, "status": "✅ OK", "size_kb": size_kb, "error": ""}
        else:
            return {"url": url, "status": f"❌ Error {response.status_code}", "size_kb": 0, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"url": url, "status": "⚠️ Failed", "size_kb": 0, "error": str(e)}

def extract_url(json_str):
    try:
        data = json.loads(json_str)
        return data.get('entries', {}).get('url')
    except:
        return None

# --- UI 介面設計 ---
tab1, tab2 = st.tabs(["批量 CSV 檢查", "單一網址檢查"])

# --- Tab 1: 批量檢查 ---
with tab1:
    st.header("上傳 CSV 進行批量掃描")
    uploaded_file = st.file_uploader("選擇您的 CSV 檔案", type=["csv"], key="batch_uploader")

    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        if 'mainImage' in df.columns:
            df['extracted_url'] = df['mainImage'].apply(extract_url)
            unique_urls = df['extracted_url'].dropna().unique().tolist()
            st.write(f"📊 偵測到 {len(unique_urls)} 個唯一網址。")

            if st.button("🚀 開始批次掃描"):
                results = []
                progress_bar = st.progress(0)
                
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_to_url = {executor.submit(check_image_size,
