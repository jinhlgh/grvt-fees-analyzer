import requests
import time
from datetime import datetime, timedelta

# ==========================================
# 核心配置区域 (Configuration) - 多账号池
# ==========================================
ACCOUNTS = [
    {
        "alias": "账号A", 
        "api_key": "YOUR_FIRST_API_KEY",
        "sub_account_id": "YOUR_FIRST_SUB_ACCOUNT_ID"
    },
    {
        "alias": "账号B",
        "api_key": "YOUR_SECOND_API_KEY",
        "sub_account_id": "YOUR_SECOND_SUB_ACCOUNT_ID"
    }
]

GRVT_AUTH_ENDPOINT = "https://edge.grvt.io/auth/api_key/login"
BASE_URL = "https://trades.grvt.io/full"

def authenticate(api_key, alias):
    print(f"🔐 正在请求 【{alias}】 的鉴权凭证...")
    headers = {"Content-Type": "application/json", "Cookie": "rm=true;"}
    payload = {"api_key": api_key}
    
    try:
        # 增加鉴权超时时间
        response = requests.post(GRVT_AUTH_ENDPOINT, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        cookie_value = response.cookies.get("gravity")
        account_id = response.headers.get("X-Grvt-Account-Id")
        if not cookie_value or not account_id:
            raise ValueError("未能提取到完整的 Cookie 或 Account-Id。")
            
        print(f"  -> ✅ 【{alias}】 鉴权成功！")
        return {"Content-Type": "application/json", "Cookie": f"gravity={cookie_value}", "X-Grvt-Account-Id": account_id}
    except Exception as e:
        print(f"  -> ❌ 【{alias}】 鉴权失败: {e}")
        return None 

def analyze_fees_last_6_months(auth_headers, sub_account_id, alias):
    url = f"{BASE_URL}/v1/fill_history"
    
    end_time_dt = datetime.now()
    start_time_dt = end_time_dt - timedelta(days=30 * 6)
    start_time_ns = str(int(start_time_dt.timestamp() * 1e9))
    end_time_ns = str(int(end_time_dt.timestamp() * 1e9))
    
    print(f"📊 正在拉取 【{alias}】 ({sub_account_id}) 的成交数据...")
    
    cursor = ""
    limit = 1000
    total_records = 0
    fees_summary = {}
    page = 1

    while True:
        payload = {
            "sub_account_id": sub_account_id,
            "limit": limit,
            "start_time": start_time_ns,
            "end_time": end_time_ns
        }
        if cursor:
            payload["cursor"] = cursor
            
        # ==========================================
        # 新增：网络防抖动与自动重试机制
        # ==========================================
        request_success = False
        data = {}
        for attempt in range(3):  # 最大重试 3 次
            try:
                # 增加了 15 秒的超时限制，防止程序死锁
                response = requests.post(url, headers=auth_headers, json=payload, timeout=15)
                response.raise_for_status() 
                data = response.json()
                request_success = True
                break  # 成功拿到数据，跳出重试循环
            except requests.exceptions.RequestException as e:
                print(f"  -> ⚠️ 【{alias}】 第 {page} 页网络异常 (尝试 {attempt+1}/3): {e}")
                time.sleep(2)  # 等待 2 秒后重试
                
        if not request_success:
            print(f"❌ 连续 3 次请求失败！为保证数据严谨，终止 【{alias}】 的拉取，当前统计可能不完整。")
            break  # 如果重试 3 次依然失败，才真正放弃这一页
            
        # ==========================================
        
        records = data.get("result") or []
        next_cursor = data.get("next", "")
        
        if not records:
            break 
            
        for record in records:
            total_records += 1
            instrument = record.get("instrument", "UNKNOWN")
            parts = instrument.split("_")
            quote_asset = parts[1] if len(parts) >= 2 else "UNKNOWN"
            
            if quote_asset not in fees_summary:
                fees_summary[quote_asset] = {
                    "maker_fee": 0.0, "taker_fee": 0.0, "total_fee": 0.0, "maker_count": 0, "taker_count": 0
                }
            
            fee_str = record.get("fee", "0")
            try:
                fee_value = float(fee_str)
            except ValueError:
                fee_value = 0.0
            
            is_taker = record.get("is_taker", True) 
            
            fees_summary[quote_asset]["total_fee"] += fee_value
            if is_taker:
                fees_summary[quote_asset]["taker_fee"] += fee_value
                fees_summary[quote_asset]["taker_count"] += 1
            else:
                fees_summary[quote_asset]["maker_fee"] += fee_value
                fees_summary[quote_asset]["maker_count"] += 1
            
        if not next_cursor or next_cursor == cursor:
            break
            
        cursor = next_cursor
        page += 1
        time.sleep(0.5)  # 成功拉取一页后，轻微休眠 0.5 秒再拉下一页，降低封控概率

    # 打印单账户分析结果
    print(f"✅ 【{alias}】 解析完成，共 {total_records} 笔有效成交")
    
    if total_records == 0:
        print("  -> 该账号在此期间没有任何成交记录。")
    else:
        for asset, stats in fees_summary.items():
            print(f"💰 结算币种: 【{asset}】")
            print(f"  ├─ 总计手续费 : {round(stats['total_fee'], 4)} {asset}")
            print(f"  │")
            print(f"  ├─ 作为 Taker : 共 {stats['taker_count']} 笔")
            print(f"  │    └── 支出 : {round(stats['taker_fee'], 4)} {asset}")
            print(f"  │")
            print(f"  └─ 作为 Maker : 共 {stats['maker_count']} 笔")
            print(f"       └── 支出 : {round(stats['maker_fee'], 4)} {asset}")

if __name__ == "__main__":
    print("="*60)
    print("🚀 GRVT 多账号对账程序启动 (带防抖动重试机制)")
    print("="*60)
    
    for idx, account in enumerate(ACCOUNTS):
        alias = account.get("alias", f"账号_{idx+1}")
        api_key = account.get("api_key")
        sub_account_id = account.get("sub_account_id")
        
        if not api_key or api_key.startswith("YOUR_"):
            print(f"\n⚠️ 提示: 检测到 【{alias}】 未配置真实密钥，已跳过。")
            continue
            
        print(f"\n" + "*"*50)
        auth_headers = authenticate(api_key, alias)
        
        if auth_headers:
            analyze_fees_last_6_months(auth_headers, sub_account_id, alias)
        
        print("*"*50)
        
        if idx < len(ACCOUNTS) - 1:
            time.sleep(1.5)
            
    print("\n🎉 所有账号批量查询及分析完毕！")