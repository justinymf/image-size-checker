import streamlit as st
import pandas as pd
import json
import asyncio
import aiohttp
import time
import random

# 設定頁面資訊
st.set_page_config(page_title="HTTP Status Checker Pro", layout="wide", page_icon="🛡️")

st.title("🛡️ 圖片 HTTP 狀態檢查工具 (抗封鎖版)")
st.markdown("""
此版本針對 **大量 URL** 進行了優化：
1. **偽裝瀏覽器** (User-Agent) 避免被識別為機器人。
2. **自動重試** (當遇到 504/429 錯誤時會自動重試)。
3. **分批處理** (每批次中間會有緩衝時間，避免被防火牆封鎖 IP)。
""")

# --- 偽裝 Header ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
}

# --- 非同步檢查核心邏輯 (含重試機制) ---
async def check_http_status(session, url, semaphore):
    """非同步檢查 HTTP Status Code，包含重試邏輯"""
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return {"url": url, "code": 0, "status": "⚠️ Invalid URL", "reason": "Malformed URL"}
    
    # 限制同時執行數量 (Semaphore)
    async with semaphore:
        retries = 3 # 設定重試次數
        for attempt in range(retries):
            try:
                # 使用 HEAD 請求
                async with session.head(url, headers=HEADERS, timeout=10, allow_redirects=True) as response:
                    code = response.status
                    reason = response.reason
                    
                    # 如果遇到 504 (Timeout) 或 429 (Too Many Requests)，且不是最後一次嘗試 -> 等待後重試
                    if code in [504, 429, 503] and attempt < retries - 1:
                        wait_time = (attempt + 1) * 2 # 等待 2秒, 4秒...
                        await asyncio.sleep(wait_time)
                        continue 

                    # 狀態碼分類
                    if code == 200:
                        status_icon = "🟢 200 OK"
                    elif code == 404:
                        status_icon = "🔴 404 Not Found"
                    elif code == 410:
                        status_icon = "🏚️ 410 Gone"
                    elif code == 403:
                        status_icon = "🟠 403 Forbidden"
                    elif code >= 500:
                        status_icon = f"🔥 {code} Server Error"
                    else:
                        status_icon = f"⚪ {code} {reason}"

                    return {
                        "url": url, 
                        "code": code, 
                        "status": status_icon, 
                        "reason": reason
                    }
            
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                # 網路錯誤也重試
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                return {"url": url, "code": 0, "status": "❌ Connection Error", "reason": str(e)}
            except Exception as e:
                return {"url": url, "code": 0, "status": "❌ Error", "reason": str(e)}

async def process_batch_smart(urls, max_concurrency, progress_bar, status_text):
    """智能分批處理，防止被封鎖"""
    
    # 限制同時連線數 (Semaphore 是更嚴格的控制)
    semaphore = asyncio.Semaphore(max_concurrency)
    
    # TCP Connector 設定
    connector = aiohttp.TCPConnector(limit=max_concurrency, ssl=False)
    
    timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=10)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        results = []
        total = len(urls)
        
        # 將 URL 分成小塊 (Chunks)，例如每 50 個一組
        chunk_size = 50 
        
        for i in range(0, total, chunk_size):
            chunk_urls = urls[i : i + chunk_size]
            chunk_tasks = []
            
            # 建立這一批的任務
            for url in chunk_urls:
                task = check_http_status(session, url, semaphore)
                chunk_tasks.append(task)
            
            # 執行這一批
            batch_results = await asyncio.gather(*chunk_tasks)
            results.extend(batch_results)
            
            # 更新進度
            current_count = min(i + chunk_size, total)
            percent = current_count / total
            progress_bar.progress(percent)
            status_text.text(f"🛡️ 掃描中 (已完成 {current_count}/{total})... 休息防封鎖中 ☕")
            
            # 關鍵：每一批做完後，稍微休息一下 (0.5 ~ 1.5 秒隨機)
            # 這能大幅減少 504 出現的機率
            if i + chunk_size < total:
                await asyncio.sleep(random.uniform(0.5, 1.5))
            
        return results

def extract_url(json_str):
    try:
        data = json.loads(json_str)
        return data.get('entries', {}).get('url')
    except:
        return None

# --- UI 介面 ---
tab1, tab2 = st.tabs(["📂 批量 CSV 檢查", "🔍 單一網址測試"])

# === Tab 1: 批量檢查 ===
with tab1:
    st.header("上傳 CSV 檢查 (安全模式)")
    
    with st.expander("⚙️ 設定與效能", expanded=True):
        st.caption("如果仍然出現大量 504，請嘗試調低此數值")
        concurrency = st.slider("同時連線數 (建議 20-50)", 10, 100, 30)
    
    uploaded_file = st.file_uploader("選擇您的 CSV 檔案", type=["csv"], key="smart_check_uploader")

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            if 'mainImage' in df.columns:
                with st.spinner("正在解析 JSON 網址..."):
                    df['extracted_url'] = df['mainImage'].apply(extract_url)
                    unique_urls = df['extracted_url'].dropna().unique().tolist()
                
                st.info(f"📊 準備檢查 {len(unique_urls)} 個網址。系統將自動分批處理以避免 504 錯誤。")

                if st.button("🚀 開始安全掃描"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    start_time = time.time()

                    # 執行智能批次處理
                    results = asyncio.run(process_batch_smart(unique_urls, concurrency, progress_bar, status_text))
                    
                    duration = time.time() - start_time
                    progress_bar.progress(1.0)
                    status_text.text(f"✅ 完成！")
                    st.success(f"🎉 檢查完畢！耗時: {duration:.2f} 秒")

                    results_df = pd.DataFrame(results)
                    
                    # 統計看板
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("🟢 200 正常", len(results_df[results_df['code'] == 200]))
                    c2.metric("🔴 404 失效", len(results_df[results_df['code'] == 404]))
                    c3.metric("🏚️ 410 移除", len(results_df[results_df['code'] == 410]))
                    c4.metric("🔥 504/Timeout", len(results_df[results_df['code'].isin([504, 408])]))
                    c5.metric("❌ 其他", len(results_df[~results_df['code'].isin([200, 404, 410, 504, 408])]))

                    if len(results_df[results_df['code'] == 504]) > 0:
                        st.warning("⚠️ 偵測到 504 Gateway Timeout。這表示伺服器忙碌或封鎖請求。請嘗試調低「同時連線數」再試一次。")

                    st.subheader("詳細結果")
                    all_statuses = sorted(results_df['status'].unique())
                    filter_option = st.multiselect("過濾狀態碼:", options=all_statuses, default=all_statuses)
                    
                    filtered_df = results_df[results_df['status'].isin(filter_option)]
                    st.dataframe(
                        filtered_df, 
                        column_config={
                            "url": st.column_config.LinkColumn("圖片網址"),
                            "status": "狀態",
                            "reason": "伺服器訊息"
                        },
                        use_container_width=True
                    )
                    
                    csv = results_df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 下載完整報告", data=csv, file_name="http_status_report.csv", mime="text/csv")
            else:
                st.error("CSV 缺少 'mainImage' 欄位！")
        except Exception as e:
            st.error(f"錯誤: {e}")

# === Tab 2: 單一檢查 ===
with tab2:
    st.header("單一網址 HTTP 測試")
    url_input = st.text_input("輸入圖片網址", placeholder="https://...")
    
    if st.button("檢查狀態"):
        if url_input:
            async def run_single():
                semaphore = asyncio.Semaphore(1) # 單一檢查不需要限制
                async with aiohttp.ClientSession() as session:
                    return await check_http_status(session, url_input, semaphore)
            
            res = asyncio.run(run_single())
            
            if res['code'] == 200:
                st.success(f"狀態: {res['status']}")
                st.image(url_input, width=300, caption="圖片預覽")
            elif res['code'] == 404:
                st.error(f"狀態: {res['status']}")
                st.warning("這張圖片已經不存在伺服器上 (Not Found)。")
            elif res['code'] == 410:
                st.error(f"狀態: {res['status']}")
                st.warning("這張圖片已被永久移除 (Gone)。")
            else:
                st.warning(f"狀態: {res['status']} | 訊息: {res['reason']}")
