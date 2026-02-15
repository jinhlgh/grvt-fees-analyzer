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
    print(f"📅 分析时间段: {start_time_dt.strftime('%Y-%m-%d')} 至 {end_time_dt.strftime('%Y-%m-%d')}")
    
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
            
        request_success = False
        data = {}
        for attempt in range(3):  
            try:
                response = requests.post(url, headers=auth_headers, json=payload, timeout=15)
                response.raise_for_status() 
                data = response.json()
                request_success = True
                break  
            except requests.exceptions.RequestException as e:
                print(f"  -> ⚠️ 【{alias}】 第 {page} 页网络异常 (尝试 {attempt+1}/3): {e}")
                time.sleep(2)  
                
        if not request_success:
            print(f"❌ 连续 3 次请求失败！终止 【{alias}】 的拉取。")
            break  
            
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
        time.sleep(0.5)  

    print(f"✅ 【{alias}】 解析完成，共 {total_records} 笔有效成交")
    if total_records > 0:
        for asset, stats in fees_summary.items():
            print(f"💰 【{asset}】 -> 总费: {round(stats['total_fee'], 4)} | Taker: {round(stats['taker_fee'], 4)} | Maker: {round(stats['maker_fee'], 4)}")
            
    # 新增：将该账号的统计结果返回，交给主程序去累加
    return total_records, fees_summary

if __name__ == "__main__":
    print("="*60)
    print("🚀 GRVT 多账号对账程序启动 (带全局合计)")
    print("="*60)
    
    # 新增：用于存储所有账号合计数据的字典
    grand_total_records = 0
    grand_fees_summary = {}
    
    for idx, account in enumerate(ACCOUNTS):
        alias = account.get("alias", f"账号_{idx+1}")
        api_key = account.get("api_key")
        sub_account_id = account.get("sub_account_id")
        
        if not api_key or api_key.startswith("YOUR_"):
            print(f"\n⚠️ 提示: 检测到 【{alias}】 未配置真实密钥，已跳过。")
            continue
            
        print(f"\n" + "-"*50)
        auth_headers = authenticate(api_key, alias)
        
        if auth_headers:
            # 获取单账号返回的统计数据
            acc_records, acc_summary = analyze_fees_last_6_months(auth_headers, sub_account_id, alias)
            
            # 累加到全局总计中
            grand_total_records += acc_records
            for asset, stats in acc_summary.items():
                if asset not in grand_fees_summary:
                    grand_fees_summary[asset] = {
                        "maker_fee": 0.0, "taker_fee": 0.0, "total_fee": 0.0, "maker_count": 0, "taker_count": 0
                    }
                grand_fees_summary[asset]["total_fee"] += stats["total_fee"]
                grand_fees_summary[asset]["taker_fee"] += stats["taker_fee"]
                grand_fees_summary[asset]["maker_fee"] += stats["maker_fee"]
                grand_fees_summary[asset]["taker_count"] += stats["taker_count"]
                grand_fees_summary[asset]["maker_count"] += stats["maker_count"]
        
        if idx < len(ACCOUNTS) - 1:
            time.sleep(1.5)
            
    # ==========================================
    # 打印最终的大合集 (Grand Total)
    # ==========================================
    print("\n" + "="*60)
    print("🏆 【全部账号全局大汇总】")
    print("="*60)
    print(f"总计有效成交笔数: {grand_total_records} 笔\n")
    
    if grand_total_records == 0:
        print("所有账号均无成交记录。")
    else:
        for asset, stats in grand_fees_summary.items():
            print(f"💎 核心资产: 【{asset}】")
            print(f"  ├─ 🌐 跨账号总手续费: {round(stats['total_fee'], 4)} {asset}")
            print(f"  │")
            print(f"  ├─ ⚔️ Taker (吃单)  : 共 {stats['taker_count']} 笔，总支出 {round(stats['taker_fee'], 4)} {asset}")
            print(f"  │")
            print(f"  └─ 🛡️ Maker (挂单)  : 共 {stats['maker_count']} 笔，总支出 {round(stats['maker_fee'], 4)} {asset}")
            print("-" * 60)
