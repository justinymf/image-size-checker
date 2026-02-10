import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import time
import random

# Page Configuration
st.set_page_config(page_title="HTTP Status Checker Pro", layout="wide", page_icon="🛡️")

st.title("🛡️ Image HTTP Status Checker (Export with SKU)")
st.markdown("""
This tool checks image URLs and generates a report including **SKU IDs**.
* **Deduplication**: Checks unique URLs only to save time.
* **Real-time Monitor**: Shows SKU ID and broken link immediately.
* **Full Export**: The final CSV will contain `skuId`, `url`, `status`, and `code`.
""")

# --- Fake User-Agent (Anti-blocking) ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# --- Async Check Logic ---
async def check_http_status(session, item, semaphore):
    url = item.get('url')
    sku = item.get('skuId', 'N/A')
    
    # Basic Validation
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return {"skuId": sku, "url": url, "code": 0, "status": "⚠️ Invalid URL"}
    
    async with semaphore:
        retries = 3
        for attempt in range(retries):
            try:
                # HEAD request for speed
                async with session.head(url, headers=HEADERS, timeout=10, allow_redirects=True) as response:
                    code = response.status
                    
                    # Retry on 504/429
                    if code in [504, 429, 503] and attempt < retries - 1:
                        await asyncio.sleep((attempt + 1) * 2)
                        continue 

                    # Status Classification
                    if code == 200: status = "🟢 200 OK"
                    elif code == 404: status = "🔴 404 Not Found"
                    elif code == 410: status = "🏚️ 410 Gone"
                    elif code == 403: status = "🟠 403 Forbidden"
                    else: status = f"⚪ {code}"

                    return {"skuId": sku, "url": url, "code": code, "status": status}
            
            except (asyncio.TimeoutError, aiohttp.ClientError):
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                return {"skuId": sku, "url": url, "code": 0, "status": "❌ Connection Error"}
            except Exception as e:
                return {"skuId": sku, "url": url, "code": 0, "status": "❌ Error"}

async def process_batch(data_list, max_concurrency, progress_bar, status_text, error_container):
    semaphore = asyncio.Semaphore(max_concurrency)
    connector = aiohttp.TCPConnector(limit=max_concurrency, ssl=False)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        # Create tasks
        for item in data_list:
            task = check_http_status(session, item, semaphore)
            tasks.append(task)
        
        results = []
        total = len(data_list)
        error_count = 0
        
        # Execute and update UI in real-time
        for i, future in enumerate(asyncio.as_completed(tasks)):
            res = await future
            results.append(res)
            
            # Show 404/410 errors immediately
            if res['code'] in [404, 410]:
                error_count += 1
                with error_container:
                    c1, c2 = st.columns([3, 1])
                    c1.error(f"❌ #{error_count} | SKU: {res['skuId']} | {res['status']} | {res['url']}")
                    c2.image(res['url'], width=80, caption="Preview")

            # Update progress bar every 50 items
            if i % 50 == 0:
                percent = (i + 1) / total
                progress_bar.progress(percent)
                status_text.text(f"Scanning... Completed {i+1} / {total} (Found {error_count} errors)")
        
        return results

# --- Main Interface ---
uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])

# Speed Control
concurrency = st.slider("Concurrent Connections (Batch Size)", 10, 100, 50)

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    
    # Auto-detect columns
    url_col = 'url' if 'url' in df.columns else None
    sku_col = 'skuId' if 'skuId' in df.columns else None
    
    if url_col:
        # Prepare Data List
        if sku_col:
            # Drop duplicates based on URL but keep the first SKU found
            df_unique = df.drop_duplicates(subset=[url_col])
            data_list = df_unique[[sku_col, url_col]].to_dict('records')
        else:
            df_unique = df.drop_duplicates(subset=[url_col])
            data_list = [{'skuId': 'N/A', 'url': row[url_col]} for _, row in df_unique.iterrows()]

        st.info(f"File loaded! Total unique URLs to check: {len(data_list)}.")
        
        # Error Monitor Container
        st.markdown("### 🚨 Real-time Error Monitor")
        error_container = st.container()

        if st.button("🚀 Start Check"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            start_time = time.time()
            results = asyncio.run(process_batch(data_list, concurrency, progress_bar, status_text, error_container))
            duration = time.time() - start_time
            
            progress_bar.progress(1.0)
            status_text.text("✅ Completed!")
            st.success(f"✅ Check finished! Duration: {duration:.2f} seconds")
            
            # Create DataFrame
            results_df = pd.DataFrame(results)
            
            # --- 🛠️ Reorder columns to ensure SKU is first ---
            cols = ['skuId', 'status', 'code', 'url']
            results_df = results_df[cols]
            
            # Metrics
            c1, c2, c3 = st.columns(3)
            c1.metric("🟢 Valid (200)", len(results_df[results_df['code'] == 200]))
            c2.metric("🔴 Broken (404/410)", len(results_df[results_df['code'].isin([404, 410])]))
            c3.metric("🟠 Other/Blocked", len(results_df[~results_df['code'].isin([200, 404, 410])]))
            
            # Download Button
            csv = results_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Full Report (with SKU)",
                data=csv,
                file_name="check_result_with_sku.csv",
                mime="text/csv"
            )
            
    else:
        st.error("Column 'url' not found in CSV. Please check the file format.")
