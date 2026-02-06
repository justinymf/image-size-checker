import streamlit as st
import pandas as pd
import json
import asyncio
import aiohttp
import time

# 設定頁面資訊
st.set_page_config(page_title="HTTP Status Checker", layout="wide", page_icon="📡")

st.title("📡 圖片 HTTP 狀態碼檢查工具")
st.markdown("""
此工具專注於檢查圖片網址的 **HTTP 回傳狀態 (Status Code)**，並將錯誤分開統計：
* **200**: 🟢 正常 (OK)
* **404**: 🔴 找不到檔案 (Not Found)
* **410**: 🏚️ 資源已移除 (Gone - 永久刪除)
* **403**: 🟠 禁止存取 (Forbidden)
* **5xx**: ⚠️ 伺服器錯誤
""")

# --- 非同步檢查核心邏輯 ---
async def check_http_status(session, url):
    """非同步檢查 HTTP Status Code"""
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return {"url": url, "code": 0, "status": "⚠️ Invalid URL", "reason": "Malformed URL"}
    
    try:
        # 使用 HEAD 請求
        async with session.head(url, timeout=5, allow_redirects=True) as response:
            code = response.status
            reason = response.reason
            
            # 狀態碼分類字串
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
            
    except asyncio.TimeoutError:
        return {"url": url, "code": 408, "status": "⏱️ Timeout", "reason": "Connection timed out"}
    except Exception as e:
        return {"url": url, "code": 0, "status": "❌ Error", "reason": str(e)}

async def process_batch(urls, max_concurrency, progress_bar, status_text):
    """控制併發數量並更新進度"""
    connector = aiohttp.TCPConnector(limit=max_concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for url in urls:
            task = check_http_status(session, url)
            tasks.append(task)
        
        results = []
        total = len(urls)
        
        for i, future in enumerate(asyncio.as_completed(tasks)):
            result = await future
            results.append(result)
            
            percent = (i + 1) / total
            progress_bar.progress(percent)
            status_text.text(f"📡 掃描中: {i + 1} / {total} ({(percent * 100):.1f}%)")
            
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
    st.header("上傳 CSV 檢查 HTTP 狀態")
    
    with st.expander("⚙️ 設定併發數 (速度控制)", expanded=False):
        concurrency = st.slider("同時連線數", 10, 200, 50)
    
    uploaded_file = st.file_uploader("選擇您的 CSV 檔案", type=["csv"], key="http_check_uploader")

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            if 'mainImage' in df.columns:
                with st.spinner("正在解析 JSON 網址..."):
                    df['extracted_url'] = df['mainImage'].apply(extract_url)
                    unique_urls = df['extracted_url'].dropna().unique().tolist()
                
                st.info(f"📊 準備檢查 {len(unique_urls)} 個網址。")

                if st.button("🚀 開始 HTTP 檢查"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    start_time = time.time()

                    results = asyncio.run(process_batch(unique_urls, concurrency, progress_bar, status_text))
                    
                    duration = time.time() - start_time
                    progress_bar.progress(1.0)
                    status_text.text(f"✅ 完成！")
                    st.success(f"🎉 檢查完畢！耗時: {duration:.2f} 秒")

                    results_df = pd.DataFrame(results)
                    
                    # --- 統計看板 (獨立顯示) ---
                    st.markdown("### 📊 狀態統計")
                    c1, c2, c3, c4, c5 = st.columns(5)
                    
                    c1.metric("🟢 200 正常", len(results_df[results_df['code'] == 200]))
                    
                    # 重點：404 和 410 分開
                    c2.metric("🔴 404 Not Found", len(results_df[results_df['code'] == 404]))
                    c3.metric("🏚️ 410 Gone", len(results_df[results_df['code'] == 410]))
                    
                    c4.metric("🟠 403 Forbidden", len(results_df[results_df['code'] == 403]))
                    
                    # 統計 5xx 或其他錯誤 (Timeout / Connect Error)
                    other_errors = len(results_df[~results_df['code'].isin([200, 404, 410, 403])])
                    c5.metric("⚠️ 其他/5xx", other_errors)

                    st.divider()

                    # --- 詳細結果 ---
                    st.subheader("詳細清單")
                    
                    # 預設不過濾，顯示所有
                    all_statuses = sorted(results_df['status'].unique())
                    filter_option = st.multiselect(
                        "過濾狀態碼:", 
                        options=all_statuses,
                        default=all_statuses
                    )
                    
                    filtered_df = results_df[results_df['status'].isin(filter_option)]
                    
                    st.dataframe(
                        filtered_df, 
                        column_config={
                            "url": st.column_config.LinkColumn("圖片網址"),
                            "status": "狀態",
                            "code": "代碼",
                            "reason": "伺服器訊息"
                        },
                        use_container_width=True
                    )
                    
                    csv = results_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 下載完整 HTTP 報告",
                        data=csv,
                        file_name="http_status_report.csv",
                        mime="text/csv"
                    )
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
                async with aiohttp.ClientSession() as session:
                    return await check_http_status(session, url_input)
            
            res = asyncio.run(run_single())
            
            # 單一檢查的顯示邏輯
            if res['code'] == 200:
                st.success(f"狀態: {res['status']}")
                st.image(url_input, width=300, caption="圖片預覽")
            elif res['code'] == 404:
                st.error(f"狀態: {res['status']}")
                st.warning("❌ 找不到檔案 (URL 路徑錯誤或檔案不存在)。")
            elif res['code'] == 410:
                st.error(f"狀態: {res['status']}")
                st.warning("🏚️ 檔案已被永久移除 (Gone)，不會再回來。")
            else:
                st.warning(f"狀態: {res['status']} | 訊息: {res['reason']}")
