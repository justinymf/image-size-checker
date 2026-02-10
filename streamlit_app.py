import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import time
import random

# 設定頁面資訊
st.set_page_config(page_title="HTTP Status Checker Pro", layout="wide", page_icon="🛡️")

st.title("🛡️ 圖片 HTTP 狀態檢查工具 (CSV 直讀版)")
st.markdown("""
此工具專門針對您的 `skuId` + `url` 格式設計：
* **200**: 🟢 正常 (OK)
* **404**: 🔴 找不到檔案 (Not Found)
* **410**: 🏚️ 資源已移除 (Gone)
* **403**: 🟠 禁止存取 (Forbidden)
""")

# --- 偽裝 Header (防封鎖) ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# --- 非同步檢查核心邏輯 ---
async def check_http_status(session, url, semaphore):
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return {"url": url, "code": 0, "status": "⚠️ Invalid URL", "reason": "Malformed URL"}
    
    async with semaphore:
        retries = 3
        for attempt in range(retries):
            try:
                # 使用 HEAD 請求加速
                async with session.head(url, headers=HEADERS, timeout=10, allow_redirects=True) as response:
                    code = response.status
                    
                    # 遇到 504/429 就重試
                    if code in [504, 429, 503] and attempt < retries - 1:
                        await asyncio.sleep((attempt + 1) * 2)
                        continue 

                    # 狀態分類
                    if code == 200: status = "🟢 200 OK"
                    elif code == 404: status = "🔴 404 Not Found"
                    elif code == 410: status = "🏚️ 410 Gone"
                    elif code == 403: status = "🟠 403 Forbidden"
                    else: status = f"⚪ {code}"

                    return {"url": url, "code": code, "status": status}
            
            except (asyncio.TimeoutError, aiohttp.ClientError):
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                return {"url": url, "code": 0, "status": "❌ Connection Error"}
            except Exception as e:
                return {"url": url, "code": 0, "status": "❌ Error"}

async def process_batch(urls, max_concurrency, progress_bar, status_text, error_container):
    semaphore = asyncio.Semaphore(max_concurrency)
    connector = aiohttp.TCPConnector(limit=max_concurrency, ssl=False)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        # 建立任務
        for url in urls:
            task = check_http_status(session, url, semaphore)
            tasks.append(task)
        
        results = []
        total = len(urls)
        error_count = 0
        
        # 執行並即時更新
        for i, future in enumerate(asyncio.as_completed(tasks)):
            res = await future
            results.append(res)
            
            # 即時顯示 404/410 錯誤
            if res['code'] in [404, 410]:
                error_count += 1
                with error_container:
                    st.error(f"❌ #{error_count} | {res['status']} | {res['url']}")

            # 更新進度條 (每 100 筆更新一次介面，避免卡頓)
            if i % 100 == 0:
                percent = (i + 1) / total
                progress_bar.progress(percent)
                status_text.text(f"掃描中... 已完成 {i+1} / {total} (發現 {error_count} 個錯誤)")
        
        return results

# --- 主介面 ---
uploaded_file = st.file_uploader("請上傳 CSV", type=["csv"])

# 速度設定
concurrency = st.slider("同時連線數 (建議 30-50)", 10, 100, 50)

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    
    # 自動偵測網址欄位 (你的檔案欄位是 'url')
    url_col = 'url' if 'url' in df.columns else None
    
    if url_col:
        urls = df[url_col].dropna().unique().tolist()
        st.info(f"檔案讀取成功！共 {len(urls)} 筆網址待檢查。")
        
        # 錯誤顯示區
        st.markdown("### 🚨 即時錯誤監控")
        error_container = st.container()

        if st.button("🚀 開始檢查"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            start_time = time.time()
            results = asyncio.run(process_batch(urls, concurrency, progress_bar, status_text, error_container))
            duration = time.time() - start_time
            
            progress_bar.progress(1.0)
            st.success(f"✅ 檢查完成！耗時 {duration:.2f} 秒")
            
            # 整理結果
            results_df = pd.DataFrame(results)
            
            # 統計
            c1, c2, c3 = st.columns(3)
            c1.metric("🟢 正常", len(results_df[results_df['code'] == 200]))
            c2.metric("🔴 失效 (404/410)", len(results_df[results_df['code'].isin([404, 410])]))
            c3.metric("🟠 其他", len(results_df[~results_df['code'].isin([200, 404, 410])]))
            
            # 下載
            csv = results_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 下載完整報告", data=csv, file_name="check_result.csv", mime="text/csv")
            
    else:
        st.error("CSV 中找不到 'url' 欄位，請檢查檔案格式。")
