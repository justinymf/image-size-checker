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
        try:
            df = pd.read_csv(uploaded_file)
            if 'mainImage' in df.columns:
                df['extracted_url'] = df['mainImage'].apply(extract_url)
                unique_urls = df['extracted_url'].dropna().unique().tolist()
                st.write(f"📊 偵測到 {len(unique_urls)} 個唯一網址。")

                if st.button("🚀 開始批次掃描"):
                    results = []
                    progress_bar = st.progress(0)
                    
                    # 這裡就是修正後的關鍵部分
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        future_to_url = {executor.submit(check_image_size, url): url for url in unique_urls}
                        for i, future in enumerate(future_to_url):
                            results.append(future.result())
                            progress_bar.progress((i + 1) / len(unique_urls))

                    results_df = pd.DataFrame(results)
                    st.dataframe(results_df, use_container_width=True)
                    
                    # 下載按鈕
                    csv = results_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 下載報告",
                        data=csv,
                        file_name="report.csv",
                        mime="text/csv"
                    )
            else:
                st.error("CSV 缺少 'mainImage' 欄位！")
        except Exception as e:
            st.error(f"讀取檔案時發生錯誤: {e}")

# --- Tab 2: 單一檢查 ---
with tab2:
    st.header("輸入單個圖片網址")
    st.markdown("您可以直接貼上圖片連結來檢查該圖片是否在線上以及它的檔案大小。")
    
    # 輸入框
    input_url = st.text_input("圖片 URL", placeholder="https://contents.mediadecathlon.com/...")

    if st.button("🔍 立即檢查"):
        if input_url:
            with st.spinner('正在連線檢查中...'):
                res = check_image_size(input_url)
                
                # 顯示結果卡片
                if res['status'] == "✅ OK":
                    st.success(f"狀態：{res['status']}")
                    c1, c2 = st.columns(2)
                    c1.metric("檔案大小", f"{res['size_kb']} KB")
                    # 嘗試顯示圖片
                    try:
                        c2.image(input_url, caption="圖片預覽", width=300)
                    except:
                        c2.warning("無法載入預覽圖")
                else:
                    st.error(f"狀態：{res['status']}")
                    st.warning(f"詳細錯誤：{res['error']}")
        else:
            st.info("請先輸入網址。")
