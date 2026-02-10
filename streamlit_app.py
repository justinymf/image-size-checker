// ==========================================
// ⚙️ 設定區 (請依照你的表格修改)
// ==========================================
var SHEET_NAME = '工作表1'; // 你的工作表名稱 (Tab Name)
var URL_COL = 2;           // 你的 "url" 在第幾欄 (B欄 = 2)
var STATUS_COL = 3;        // 你的 "Image status" 在第幾欄 (C欄 = 3)
var START_ROW = 2;         // 從第幾行開始 (避開標題列)
var MAX_EXECUTION_TIME = 280; // 執行時間限制 (秒)

// ==========================================
// 1️⃣ 選單與主功能
// ==========================================

/**
 * 建立 Google Sheet 選單
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('圖片檢查工具 🚀')
    .addItem('▶️ 開始檢查 (直接讀取 URL)', 'startRowByRowScanning')
    .addItem('🔄 重置進度', 'resetProgress')
    .addItem('🛑 停止所有排程', 'stopTrigger')
    .addToUi();
}

/**
 * 重置進度
 */
function resetProgress() {
  var props = PropertiesService.getScriptProperties();
  props.deleteProperty('LAST_ROW');
  stopTrigger();
  SpreadsheetApp.getActiveSpreadsheet().toast('已重置！請點擊「開始」從頭掃描。', '重置完成');
}

/**
 * 停止排程
 */
function stopTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
  SpreadsheetApp.getActiveSpreadsheet().toast('自動排程已停止。');
}

// ==========================================
// 2️⃣ 核心掃描邏輯
// ==========================================

/**
 * 主程式：逐行讀取 Column B 的 URL 並檢查
 */
function startRowByRowScanning() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  if (!sheet) {
    SpreadsheetApp.getUi().alert('❌ 找不到工作表: "' + SHEET_NAME + '"，請修改程式碼第 4 行。');
    return;
  }

  // 讀取上次進度
  var props = PropertiesService.getScriptProperties();
  var currentRow = parseInt(props.getProperty('LAST_ROW')) || START_ROW;
  var lastRow = sheet.getLastRow();

  // 檢查是否完成
  if (currentRow > lastRow) {
    SpreadsheetApp.getUi().alert('✅ 所有網址檢查完畢！');
    stopTrigger();
    props.deleteProperty('LAST_ROW');
    return;
  }

  // 顯示提示
  if (currentRow === START_ROW) {
    SpreadsheetApp.getActiveSpreadsheet().toast('🚀 正在讀取 Column ' + URL_COL + ' 的網址進行檢查...', '開始');
  }

  var startTime = (new Date()).getTime();

  // --- 逐行迴圈 ---
  for (var i = currentRow; i <= lastRow; i++) {
    
    // ⏰ 時間監控 (4分40秒自動暫停)
    var currentTime = (new Date()).getTime();
    if ((currentTime - startTime) / 1000 > MAX_EXECUTION_TIME) {
      props.setProperty('LAST_ROW', i);
      createTrigger(); // 設定 1 分鐘後自動重啟
      SpreadsheetApp.getActiveSpreadsheet().toast('⏳ 休息 1 分鐘後自動繼續... (目前進度: Row ' + i + ')');
      return;
    }

    // 1. 直接讀取儲存格
    var urlCell = sheet.getRange(i, URL_COL);     // 讀取 "url" (Column 2)
    var statusCell = sheet.getRange(i, STATUS_COL); // 準備寫入 "Image status" (Column 3)
    
    var url = urlCell.getValue();
    var currentStatus = statusCell.getValue();

    // 2. 邏輯判斷：URL 唔係空，而且 Status 係空，先至去 Check
    if (url !== "" && (currentStatus === "" || currentStatus === null)) {
      
      // 確保 url 係字串並移除前後空格
      var cleanUrl = url.toString().trim();
      
      var result = checkUrl(cleanUrl); // 呼叫檢查函數
      
      statusCell.setValue(result); // 寫入結果
      
      // 🔥 強制刷新畫面 (即時顯示)
      SpreadsheetApp.flush(); 
    }

    // 更新進度
    props.setProperty('LAST_ROW', i + 1);
  }

  stopTrigger();
  props.deleteProperty('LAST_ROW');
  SpreadsheetApp.getActiveSpreadsheet().toast('🎉 全部完成！');
}

// ==========================================
// 3️⃣ 網址檢查功能
// ==========================================

/**
 * 檢查單一網址狀態 (無須 JSON parse，直接當網址用)
 */
function checkUrl(url) {
  // 基本格式檢查
  if (!url || !url.startsWith('http')) return "⚠️ 無效網址";
  
  try {
    // 策略：使用 GET Range (只下載前 10 bytes) 
    // 這是最快且最不容易被 Block 的方法
    var options = {
      'method': 'get', 
      'headers': {
        'Range': 'bytes=0-10', 
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
      },
      'muteHttpExceptions': true,       
      'followRedirects': true,          
      'validateHttpsCertificates': false 
    };
    
    var response = UrlFetchApp.fetch(url, options);
    var code = response.getResponseCode();
    
    // 🛑 緩衝 (避免太快被封 IP)
    Utilities.sleep(50); 
    
    // --- 狀態碼對應表 ---
    if (code === 200 || code === 206) return "🟢 200"; // 206 = Partial Content (成功)
    if (code === 404) return "🔴 404";
    if (code === 410) return "🏚️ 410";
    if (code === 403) return "🟠 403";
    if (code === 429) return "⏳ 429";
    if (code >= 500) return "🔥 " + code;
    
    return "⚠️ " + code;
    
  } catch (e) {
    var msg = e.message;
    if (msg.includes("Address unavailable") || msg.includes("DNS")) return "❌ DNS Error";
    if (msg.includes("Timeout")) return "⏱️ Timeout";
    return "❌ " + msg;
  }
}

// ==========================================
// 4️⃣ 自動化觸發器
// ==========================================

function createTrigger() {
  stopTrigger();
  ScriptApp.newTrigger('startRowByRowScanning')
    .timeBased()
    .after(60 * 1000)
    .create();
}
