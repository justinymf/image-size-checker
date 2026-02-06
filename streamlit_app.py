import streamlit as st
import pandas as pd
import json
import asyncio
import aiohttp
import time

# 設定頁面
st.set_page_config(page_title="Ultra Image Checker", layout="wide", page_icon="⚡")
st.title("⚡ 極速圖片網址檢查工具 (AsyncIO 版)")

# --- 非同步檢查核心邏輯 ---
async def check_url_async(session, url):
    """非同步檢查單一網址"""
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return {"url": url, "status": "⚠️ Invalid URL", "size_kb": 0, "error": "Malformed URL"}
    
    try:
        # 使用 HEAD 請求，timeout 設定為 5 秒
        async with session.head(url, timeout=5, allow_redirects=True) as response:
            if response.status == 200:
                size_bytes = int(response.headers.get('Content-Length', 0))
                size_kb = round(size_bytes / 1024, 2)
                return {"url": url, "status": "✅ OK", "size_kb": size_kb, "error": ""}
            else:
                return {"url": url, "status": f"❌ Error {response.status}", "size_kb": 0, "error": f"HTTP {response.status}"}
    except Exception as e:
        return {"url": url, "status": "⚠️ Failed", "size_kb": 0, "error": str(e)}

async def process_batch(urls, max_concurrency, progress_bar, status_text):
    """控制併發數量並更新進度"""
    connector = aiohttp.TCPConnector(limit=max_concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for url in urls:
            task = check_url_async(session, url)
            tasks.append(task)
        
        results = []
        total = len(urls)
        
        # 使用 as_completed 讓完成的任務立即回傳，以更新進度條
        for i, future in enumerate(asyncio.as_completed(tasks)):
            result = await future
            results.append(result)
            
            # 更新進度
            percent = (i + 1) / total
            progress_bar.progress(percent)
            status_text.text(f"🚀 正在檢查: {i + 1} / {total} ({(percent * 100):.1f}%)")
            
        return results

def extract_url(json_str):
    try:
        data = json.loads(json_str)
        return data.get('entries', {}).get('url')
    except:
        return None

# --- UI 介面 ---
tab1, tab2 = st.tabs(["⚡ 批量極速檢查", "🔍 單一網址檢查"])

# === Tab 1: 批量檢查 ===
with tab1:
    st.header("上傳 CSV 進行大量掃描")
    
    # 側邊欄設定
    with st.expander("⚙️ 進階設定 (速度控制)", expanded=True):
        concurrency = st.slider(
            "同時併發連線數 (Batch Size)", 
            min_value=10, 
            max_value=200, 
            value=50, 
            help="數值越高越快，但可能導致伺服器阻擋。建議設定 50-100。"
        )
    
    uploaded_file = st.file_uploader("選擇您的 CSV 檔案", type=["csv"], key="batch_async")

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            if 'mainImage' in df.columns:
                df['extracted_url'] = df['mainImage'].apply(extract_url)
                unique_urls = df['extracted_url'].dropna().unique().tolist()
                
                st.info(f"📊 檔案讀取成功！準備檢查 {len(unique_urls)} 個網址。")

                if st.button("🚀 開始極速掃描"):
                    # 初始化 UI 元件
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    start_time = time.time()

                    # 執行 AsyncIO
                    results = asyncio.run(process_batch(unique_urls, concurrency, progress_bar, status_text))
                    
                    end_time = time.time()
                    duration = end_time - start_time
                    
                    # 顯示完成訊息
                    progress_bar.progress(1.0)
                    status_text.text(f"✅ 檢查完成！")
                    st.success(f"🎉 全部完成！耗時: {duration:.2f} 秒 (平均每秒 {len(unique_urls)/duration:.1f} 張)")

                    # 統計與顯示
                    results_df = pd.DataFrame(results)
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("✅ 正常", len(results_df[results_df['status'] == "✅ OK"]))
                    c2.metric("❌ 異常", len(results_df[results_df['status'] != "✅ OK"]))
                    c3.metric("⚠️ 失敗", len(results_df[results_df['status'] == "⚠️ Failed"]))

                    st.dataframe(results_df, use_container_width=True)
                    
                    # 下載
                    csv = results_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 下載完整報告",
                        data=csv,
                        file_name="async_image_report.csv",
                        mime="text/csv"
                    )
            else:
                st.error("CSV 缺少 'mainImage' 欄位！")
        except Exception as e:
            st.error(f"錯誤: {e}")

# === Tab 2: 單一檢查 (保持不變) ===
with tab2:
    st.header("單一網址快速測試")
    url_input = st.text_input("輸入圖片網址")
    if st.button("檢查"):
        if url_input:
            async def run_single():
                async with aiohttp.ClientSession() as session:
                    return await check_url_async(session, url_input)
            
            res = asyncio.run(run_single())
            if res['status'] == "✅ OK":
                st.success(f"狀態: {res['status']} | 大小: {res['size_kb']} KB")
                st.image(url_input, width=300)
            else:
                st.error(f"狀態: {res['status']} | 錯誤: {res['error']}")
