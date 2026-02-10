import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import time

# --- Page Configuration ---
st.set_page_config(page_title="HTTP Status Checker Pro", layout="wide", page_icon="🛡️")

st.title("🛡️ Image HTTP Status Checker")
st.markdown("""
This tool automatically detects `skuId` or `skuGroupId` and performs high-speed asynchronous checks.
* **Smart Detection**: Supports various SKU column naming conventions.
* **Async Engine**: Checked using non-blocking HTTP requests.
""")

# --- Constants ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# --- Async Core Logic ---
async def check_http_status(session, item, semaphore, id_col_name):
    url = item.get('url')
    id_val = item.get('id_val', 'N/A')
    
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return {id_col_name: id_val, "url": url, "code": 0, "status": "⚠️ Invalid URL"}
    
    async with semaphore:
        try:
            # Using HEAD request for performance
            async with session.head(url, headers=HEADERS, timeout=12, allow_redirects=True) as response:
                code = response.status
                status_map = {
                    200: "🟢 200 OK", 
                    404: "🔴 404 Not Found", 
                    410: "🏚️ 410 Gone", 
                    403: "🟠 403 Forbidden"
                }
                status = status_map.get(code, f"⚪ {code}")
                return {id_col_name: id_val, "url": url, "code": code, "status": status}
        except Exception:
            return {id_col_name: id_val, "url": url, "code": 0, "status": "❌ Connection Error"}

async def run_checker(data_list, concurrency, id_col_name, progress_bar, status_text, error_container):
    semaphore = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(ssl=False, limit=0)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_http_status(session, item, semaphore, id_col_name) for item in data_list]
        results = []
        
        for i, future in enumerate(asyncio.as_completed(tasks)):
            res = await future
            results.append(res)
            
            # Real-time Issue Monitor
            if res['code'] != 200:
                with error_container:
                    st.warning(f"ID: {res[id_col_name]} | {res['status']} | {res['url']}")
            
            # Update Progress UI
            if i % 10 == 0 or i == len(tasks) - 1:
                progress = (i + 1) / len(tasks)
                progress_bar.progress(progress)
                status_text.text(f"Processed: {i+1} / {len(tasks)}")
                
        return results

# --- Main UI Interface ---
st.sidebar.header("Settings")
uploaded_file = st.sidebar.file_uploader("Upload CSV File", type=["csv"])
concurrency = st.sidebar.slider("Concurrency (Speed)", 10, 100, 50, help="Higher is faster but may trigger server blocking.")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    cols = df.columns.tolist()
    
    # 1. Dynamic Column Detection
    url_col = next((c for c in cols if 'url' in c.lower()), None)
    
    # Priority: skuGroupId > skuId > anything with 'sku'
    id_col = None
    if any('skugroup' in c.lower() for c in cols):
        id_col = next(c for c in cols if 'skugroup' in c.lower())
    elif any('skuid' in c.lower() for c in cols):
        id_col = next(c for c in cols if 'skuid' in c.lower())
    elif any('sku' in c.lower() for c in cols):
        id_col = next(c for c in cols if 'sku' in c.lower())

    if not url_col or not id_col:
        st.error(f"Required columns missing! Found: {cols}")
        st.info("Tip: CSV must contain a 'url' column and an ID column (e.g., 'skuId' or 'skuGroupId').")
    else:
        st.info(f"Detected ID Column: `{id_col}` | URL Column: `{url_col}`")
        
        # Deduplication and Data Prep
        df_unique = df.drop_duplicates(subset=[url_col]).copy()
        process_data = [
            {'id_val': row[id_col], 'url': row[url_col]} 
            for _, row in df_unique.iterrows()
        ]

        st.write(f"Total unique URLs to check: **{len(process_data)}**")
        
        error_monitor = st.expander("🚨 Real-time Issue Monitor", expanded=True)
        error_container = error_monitor.container()

        if st.button("🚀 Run Status Check"):
            p_bar = st.progress(0)
            s_text = st.empty()
            
            # Start Async Loop
            start_time = time.time()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final_results = loop.run_until_complete(
                run_checker(process_data, concurrency, id_col, p_bar, s_text, error_container)
            )
            
            duration = time.time() - start_time
            st.success(f"Finished in {duration:.2f} seconds!")
            
            # 2. Result Processing & Download
            res_df = pd.DataFrame(final_results)
            # Ensure ID column is first
            display_cols = [id_col, 'status', 'code', 'url']
            res_df = res_df[display_cols]
            
            st.divider()
            st.subheader("📊 Final Report")
            
            # Metrics
            c1, c2, c3 = st.columns(3)
            c1.metric("200 OK", len(res_df[res_df['code'] == 200]))
            c2.metric("Errors/Broken", len(res_df[res_df['code'] != 200]))
            c3.metric("Total Unique", len(res_df))

            st.dataframe(res_df, use_container_width=True)
            
            csv_bytes = res_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Download Report ({id_col})",
                data=csv_bytes,
                file_name=f"check_results_{int(time.time())}.csv",
                mime="text/csv"
            )
