import streamlit as st
import pandas as pd
import json
import asyncio
import aiohttp
import time
import random

# 設定頁面資訊
st.set_page_config(page_title="HTTP Status Checker Pro", layout="wide", page_icon="🛡️")

st.title("🛡️ 圖片 HTTP 狀態檢查工具 (即時 410 監控版)")
st.markdown("""
此版本包含 **410 即時監控功能**：
* 當系統偵測到 **410 Gone** 時，會立刻在下方顯示該連結。
* 系統會嘗試顯示該圖片（因為已移除，您應該會看到「破圖」圖示）。
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
    
    # 限制同時執行數量
    async with semaphore:
        retries = 3
        for attempt in range(retries):
            try:
                # 使用 HEAD 請求
                async with session.head(url, headers=HEADERS, timeout=10, allow_redirects=True) as response:
                    code = response.status
                    reason = response.reason
                    
                    if code in [504, 429, 503] and attempt < retries - 1:
                        wait_time = (attempt + 1) * 2
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
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                return {"url": url, "code": 0, "status": "❌ Connection Error", "reason": str(e)}
            except Exception as e:
                return {"url": url, "code": 0, "status": "❌ Error", "reason": str(e)}

async def process_batch_smart(urls, max_concurrency, progress_bar, status_text, error_container, show_broken_img):
    """智能分批處理，並即時回報 410"""
    
    semaphore = asyncio.Semaphore(max_concurrency)
    connector = aiohttp.TCPConnector(limit=max_concurrency, ssl=False)
    timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=10)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        results = []
        total = len(urls)
        chunk_size = 50 
        
        # 用來計算即時錯誤數量
        error_count_410 = 0
        
        for i in range(0, total, chunk_size):
            chunk_urls = urls[i : i + chunk_size]
            chunk_tasks = []
            
            for url in chunk_urls:
                task = check_http_status(session, url, semaphore)
                chunk_tasks.append(task)
            
            # 執行並等待這一批完成
            batch_results = await asyncio.gather(*chunk_tasks)
            
            # --- 🚀 即時檢查這一批的結果 ---
            for res in batch_results:
                if res['code'] == 410:
                    error_count_410 += 1
                    # 在專屬區域顯示錯誤
                    with error_container:
                        # 使用 columns 讓排版整齊：左邊文字，右邊(嘗試顯示)圖片
                        c1, c2 = st.columns([3, 1])
                        c1.error(f"#{error_count_410} | 🏚️ 410 Gone: {res['url']}")
                        if show_broken_img:
                            # 嘗試渲染圖片，讓使用者看到「破圖」圖示
                            c2.image(res['url'], caption="預覽", width=100, output_format="JPEG")
            
            results.extend(batch_results)
            
            # 更新進度
            current_count = min(i + chunk_size, total)
            percent = current_count / total
            progress_bar.progress(percent)
            status_text.text(f"🛡️ 掃描中 ({current_count}/{total})... 發現 {error_count_410} 個 410 錯誤")
            
            # 呼吸時間
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
    st.header("上傳 CSV 檢查 (含即時監控)")
    
    col_a, col_b = st.columns(2)
    with col_a:
        concurrency = st.slider("同時連線數 (Batch Size)", 10, 100, 30)
    with col_b:
        # 新增開關：是否要顯示 410 的破圖
        show_broken_img = st.checkbox("即時顯示 410 圖片預覽 (會顯示破圖圖示)", value=True)
    
    uploaded_file = st.file_uploader("選擇您的 CSV 檔案", type=["csv"], key="smart_check_uploader")

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            if 'mainImage' in df.columns:
                with st.spinner("正在解析 JSON 網址..."):
                    df['extracted_url'] = df['mainImage'].apply(extract_url)
                    unique_urls = df['extracted_url'].dropna().unique().tolist()
                
                st.info(f"📊 準備檢查 {len(unique_urls)} 個網址。")

                # 建立一個空的容器，專門用來放即時錯誤
                st.markdown("### 🚨 即時 410 錯誤監控 (Real-time Monitor)")
                error_container = st.container()
                
                # 給容器一個固定高度的 Scroll (透過 CSS hack 可選，暫時保持預設)
                # 這裡會隨著錯誤增加而變長

                if st.button("🚀 開始掃描"):
                    # 清空之前的錯誤顯示 (Streamlit 重新執行會自動清空，但如果是連續按鈕操作則需注意)
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    start_time = time.time()

                    # 執行 AsyncIO，並傳入 container
                    results = asyncio.run(process_batch_smart(
                        unique_urls, 
                        concurrency, 
                        progress_bar, 
                        status_text, 
                        error_container,
                        show_broken_img
                    ))
                    
                    duration = time.time() - start_time
                    progress_bar.progress(1.0)
                    status_text.text(f"✅ 完成！")
                    st.success(f"🎉 檢查完畢！耗時: {duration:.2f} 秒")

                    results_df = pd.DataFrame(results)
                    
                    # 統計看板
                    st.divider()
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("🟢 200 正常", len(results_df[results_df['code'] == 200]))
                    c2.metric("🔴 404 失效", len(results_df[results_df['code'] == 404]))
                    c3.metric("🏚️ 410 移除", len(results_df[results_df['code'] == 410]))
                    c4.metric("🔥 504/Timeout", len(results_df[results_df['code'].isin([504, 408])]))
                    c5.metric("❌ 其他", len(results_df[~results_df['code'].isin([200, 404, 410, 504, 408])]))

                    st.subheader("詳細結果列表")
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
                semaphore = asyncio.Semaphore(1)
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
                # 單一檢查也嘗試顯示，以證明它破圖
                st.image(url_input, width=300, caption="嘗試載入(應為破圖)")
            else:
                st.warning(f"狀態: {res['status']} | 訊息: {res['reason']}")
