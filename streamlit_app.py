import streamlit as st
import pandas as pd
import json
import requests
from concurrent.futures import ThreadPoolExecutor
import time

# 設定頁面資訊
st.set_page_config(page_title="Image URL Checker", layout="wide")

st.title("🖼️ 圖片網址與檔案大小檢查工具")
st.markdown("""
這個工具會讀取 CSV 檔案中的 `mainImage` 欄位，提取 URL 並檢查圖片是否可以正常存取。
""")

# 1. 檔案上傳
uploaded_file = st.file_uploader("請上傳 CSV 檔案", type=["csv"])

def extract_url(json_str):
    try:
        # 處理雙重轉義或標準 JSON 格式
        data = json.loads(json_str)
        return data.get('entries', {}).get('url')
    except:
        return None

def check_image_size(url):
    """檢查單張圖片的大小與狀態"""
    try:
        # 使用 HEAD 請求節省頻寬
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            size_bytes = int(response.headers.get('Content-Length', 0))
            size_kb = round(size_bytes / 1024, 2)
            return {"url": url, "status": "✅ OK", "size_kb": size_kb, "error": ""}
        else:
            return {"url": url, "status": f"❌ Error {response.status_code}", "size_kb": 0, "error": "HTTP Error"}
    except Exception as e:
        return {"url": url, "status": "⚠️ Failed", "size_kb": 0, "error": str(e)}

if uploaded_file is not None:
    # 讀取數據
    df = pd.read_csv(uploaded_file)
    
    if 'mainImage' not in df.columns:
        st.error("找不到 'mainImage' 欄位，請檢查 CSV 格式。")
    else:
        # 解析網址
        df['extracted_url'] = df['mainImage'].apply(extract_url)
        unique_urls = df['extracted_url'].dropna().unique().tolist()
        
        st.info(f"檔案讀取成功！共有 {len(df)} 筆資料，其中包含 {len(unique_urls)} 個不重複的圖片網址。")

        # 2. 開始檢查按鈕
        if st.button("🚀 開始檢查圖片大小"):
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 使用 ThreadPoolExecutor 加速網路請求
            start_time = time.time()
            max_workers = 10  # 同時開啟 10 個連線
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任務
                future_to_url = {executor.submit(check_image_size, url): url for url in unique_urls}
                
                for i, future in enumerate(future_to_url):
                    res = future.result()
                    results.append(res)
                    
                    # 更新進度條
                    progress = (i + 1) / len(unique_urls)
                    progress_bar.progress(progress)
                    status_text.text(f"檢查中: {i+1}/{len(unique_urls)}")

            end_time = time.time()
            st.success(f"檢查完成！耗時: {round(end_time - start_time, 2)} 秒")

            # 3. 顯示結果
            results_df = pd.DataFrame(results)
            
            # 統計數據
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("正常數量", len(results_df[results_df['status'] == "✅ OK"]))
            with col2:
                st.metric("異常數量", len(results_df[results_df['status'] != "✅ OK"]))
            with col3:
                st.metric("平均大小 (KB)", round(results_df[results_df['size_kb'] > 0]['size_kb'].mean(), 2) if not results_df.empty else 0)

            # 顯示結果列表
            st.subheader("詳細結果清單")
            
            # 篩選功能
            filter_status = st.multiselect("過濾狀態", options=results_df['status'].unique(), default=results_df['status'].unique())
            filtered_results = results_df[results_df['status'].isin(filter_status)]
            
            st.dataframe(filtered_results, use_container_width=True)

            # 4. 下載報告
            csv_data = filtered_results.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 下載檢查報告 (CSV)",
                data=csv_data,
                file_name="image_check_report.csv",
                mime="text/csv",
            )
