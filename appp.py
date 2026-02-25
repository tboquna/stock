import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_gsheets import GSheetsConnection
import requests
from datetime import datetime, timedelta

# 網頁基本設定
st.set_page_config(page_title="台股持股監控面板", page_icon="📈", layout="wide")

# ==========================================
# 1. 建立 Google Sheets 連線與資料初始化
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def update_gsheets(data_list):
    new_df = pd.DataFrame(data_list)
    if not new_df.empty:
        new_df = new_df[["群組", "股票代號", "股票名稱", "持有股數", "平均成本", "目標股數"]]
    conn.update(worksheet="Portfolio", data=new_df)

# 🔥 新增：自選股池的更新函式
def update_watchlist_gsheets(data_list):
    new_df = pd.DataFrame(data_list)
    if not new_df.empty:
        new_df = new_df[["股票代號", "股票名稱", "備註"]]
    conn.update(worksheet="Watchlist", data=new_df)

if 'portfolio' not in st.session_state:
    try:
        df_portfolio = conn.read(worksheet="Portfolio", ttl=0)
        df_portfolio = df_portfolio.dropna(subset=["股票代號"])
        df_portfolio["股票代號"] = df_portfolio["股票代號"].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(4)
        st.session_state.portfolio = df_portfolio.to_dict('records')
    except Exception as e:
        st.session_state.portfolio = [
            {"群組": "半導體", "股票代號": "2330", "股票名稱": "台積電", "持有股數": 1000, "平均成本": 650.0, "目標股數": 2000},
            {"群組": "ETF", "股票代號": "0050", "股票名稱": "元大台灣50", "持有股數": 2000, "平均成本": 140.0, "目標股數": 1000}
        ]

for item in st.session_state.portfolio:
    if "群組" not in item: item["群組"] = "其他"
    if "目標股數" not in item: item["目標股數"] = item.get("持有股數", 1000)

# 🔥 新增：初始化自選股清單
if 'watchlist' not in st.session_state:
    try:
        df_watch = conn.read(worksheet="Watchlist", ttl=0)
        df_watch = df_watch.dropna(subset=["股票代號"])
        df_watch["股票代號"] = df_watch["股票代號"].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(4)
        st.session_state.watchlist = df_watch.to_dict('records')
    except Exception:
        st.session_state.watchlist = [
            {"股票代號": "2330", "股票名稱": "台積電", "備註": "權王觀察指標"}
        ]

# ==========================================
# 2. 側邊欄 (Sidebar) - 分頁導覽
# ==========================================
st.sidebar.title("🧭 網站導覽")
page = st.sidebar.radio("選擇頁面", [
    "📊 個人持股監控", 
    "🌟 自選股觀察池", 
    "⚡ 當沖開盤環境評估", 
    "🏦 盤後籌碼主力追蹤", 
    "😱 市場恐慌指數 (VIX)", 
    "🔍 個股 K 線與進場分析"
])
st.sidebar.divider()

# ==========================================
# 3. 核心資料抓取函式
# ==========================================
@st.cache_data(ttl=60)
def fetch_stock_history(ticker, period="6mo"):
    try:
        stock = yf.Ticker(f"{ticker}.TW")
        hist = stock.history(period=period)
        if not hist.empty: return hist, f"{ticker}.TW"
    except Exception: pass
    try:
        stock_otc = yf.Ticker(f"{ticker}.TWO")
        hist_otc = stock_otc.history(period=period)
        if not hist_otc.empty: return hist_otc, f"{ticker}.TWO"
    except Exception: pass
    return None, None

@st.cache_data(ttl=3600)
def fetch_institutional(ticker):
    start_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": str(ticker), "start_date": start_date}
    try:
        res = requests.get(url, params=params, timeout=5)
        data = res.json()
        if data.get("msg") == "success" and len(data.get("data", [])) > 0:
            df = pd.DataFrame(data["data"])
            df['net'] = df['buy'] - df['sell']
            name_map = {"Foreign_Investor": "外資", "Investment_Trust": "投信", "Dealer_self": "自營商(自有)", "Dealer_Hedging": "自營商(避險)"}
            df['name'] = df['name'].map(name_map).fillna(df['name'])
            pivot_df = df.pivot_table(index='date', columns='name', values='net', aggfunc='sum').fillna(0)
            pivot_df = (pivot_df / 1000).round(0).astype(int)
            if '三大法人合計' not in pivot_df.columns: pivot_df['三大法人合計'] = pivot_df.sum(axis=1)
            expected_cols = ['外資', '投信', '自營商(自有)', '自營商(避險)', '三大法人合計']
            final_cols = [c for c in expected_cols if c in pivot_df.columns]
            return pivot_df[final_cols].sort_index(ascending=False).head(10)
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_margin(ticker):
    start_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockMarginPurchaseShortSale", "data_id": str(ticker), "start_date": start_date}
    try:
        res = requests.get(url, params=params, timeout=5)
        data = res.json()
        if data.get("msg") == "success" and len(data.get("data", [])) > 0:
            df = pd.DataFrame(data["data"])
            df.set_index('date', inplace=True)
            df['融資餘額(張)'] = (df['MarginPurchaseTodayBalance'] / 1000).round(0)
            df['融券餘額(張)'] = (df['ShortSaleTodayBalance'] / 1000).round(0)
            df['融資增減'] = df['融資餘額(張)'].diff()
            df['融券增減'] = df['融券餘額(張)'].diff()
            return df[['融資增減', '融券增減', '融資餘額(張)', '融券餘額(張)']].sort_index(ascending=False).head(10)
    except: pass
    return pd.DataFrame()

# -------------------------------------------------------------------
# 分頁 A：個人持股監控
# -------------------------------------------------------------------
if page == "📊 個人持股監控":
    st.title("📈 台股個人持股監控面板")
    st.sidebar.header("⚙️ 持股管理")
    
    default_categories = ["半導體", "電子零組件", "電腦及週邊", "金融股", "航運股", "生技醫療", "ETF", "其他"]
    existing_groups = list(set([item.get("群組", "其他") for item in st.session_state.portfolio]))
    combined_groups = list(set(default_categories + existing_groups))
    combined_groups.sort()
    combined_groups.append("➕ 自訂新群組...")
    
    with st.sidebar.expander("➕ 新增持股", expanded=False):
        selected_group = st.selectbox("群組分類", combined_groups)
        if selected_group == "➕ 自訂新群組...":
            new_group = st.text_input("請輸入自訂群組名稱", placeholder="如: 網通股")
        else:
            new_group = selected_group
            
        new_ticker = st.text_input("股票代號 (如: 2317)", placeholder="輸入純數字代號")
        new_name = st.text_input("股票名稱 (如: 鴻海)")
        new_shares = st.number_input("持有股數", min_value=1, step=100, value=1000)
        new_cost = st.number_input("平均成本", min_value=0.0, step=0.1, value=100.0)
        new_target = st.number_input("🎯 目標持有股數", min_value=0, step=100, value=int(new_shares))
        
        if st.button("確認新增", type="primary"):
            if new_ticker and new_name and new_group:
                existing_tickers = [item["股票代號"] for item in st.session_state.portfolio]
                if new_ticker in existing_tickers: st.sidebar.error("已在清單中！")
                else:
                    st.session_state.portfolio.append({
                        "群組": new_group.strip(), "股票代號": new_ticker.strip(), 
                        "股票名稱": new_name, "持有股數": new_shares, "平均成本": new_cost, "目標股數": new_target
                    })
                    try: update_gsheets(st.session_state.portfolio)
                    except: pass
                    st.rerun()

    with st.sidebar.expander("✏️ 修改 / 🗑️ 刪除持股", expanded=True):
        if len(st.session_state.portfolio) > 0:
            ticker_options = [item['股票代號'] for item in st.session_state.portfolio]
            def get_stock_name(ticker):
                for item in st.session_state.portfolio:
                    if item["股票代號"] == ticker:
                        name = item.get("股票名稱", "")
                        return str(name) if name and not pd.isna(name) and str(name).strip() != "" and str(name).lower() != "nan" else str(ticker)
                return str(ticker)

            selected_ticker = st.selectbox("選擇要操作的股票", ticker_options, format_func=get_stock_name)
            current_item = next(item for item in st.session_state.portfolio if item["股票代號"] == selected_ticker)
            current_group = current_item.get("群組", "其他")
            
            edit_groups_list = combined_groups.copy()
            if current_group not in edit_groups_list and current_group != "➕ 自訂新群組...":
                edit_groups_list.insert(0, current_group)
                
            edit_group_choice = st.selectbox("更新群組分類", edit_groups_list, index=edit_groups_list.index(current_group) if current_group in edit_groups_list else 0)
            if edit_group_choice == "➕ 自訂新群組...": edit_group = st.text_input("請輸入自訂群組名稱", value=current_group)
            else: edit_group = edit_group_choice
                
            edit_shares = st.number_input("更新持有股數", value=int(current_item["持有股數"]), step=100)
            edit_cost = st.number_input("更新平均成本", value=float(current_item["平均成本"]), step=0.1)
            edit_target = st.number_input("🎯 更新目標股數 (可設為0以清空)", value=int(current_item.get("目標股數", edit_shares)), min_value=0, step=100)
            
            col1, col2 = st.columns(2)
            if col1.button("更新數值"):
                current_item["群組"] = edit_group
                current_item["持有股數"] = edit_shares
                current_item["平均成本"] = edit_cost
                current_item["目標股數"] = edit_target
                try: update_gsheets(st.session_state.portfolio)
                except: pass
                st.rerun()
            if col2.button("刪除這檔", type="primary"):
                st.session_state.portfolio = [item for item in st.session_state.portfolio if item["股票代號"] != selected_ticker]
                try: update_gsheets(st.session_state.portfolio)
                except: pass
                st.rerun()

    if len(st.session_state.portfolio) == 0:
        st.info("👋 目前投資組合為空，請從左側新增持股！")
        st.stop()

    st.markdown("### 📁 投資組合總覽")
    active_groups = list(set([item["群組"] for item in st.session_state.portfolio]))
    filter_options = ["全部"] + active_groups
    selected_filter = st.selectbox("選擇檢視群組", filter_options)
    
    filtered_portfolio = st.session_state.portfolio if selected_filter == "全部" else [item for item in st.session_state.portfolio if item["群組"] == selected_filter]

    portfolio_data = []
    total_cost = total_value = total_buy_cash = total_sell_cash = 0

    for item in filtered_portfolio:
        hist, _ = fetch_stock_history(item["股票代號"], period="1d")
        current_price = round(hist['Close'].iloc[-1], 2) if hist is not None else 0
        
        cost = item["平均成本"] * item["持有股數"]
        value = current_price * item["持有股數"] if current_price else 0
        profit = value - cost
        profit_percent = (profit / cost * 100) if cost > 0 else 0
        
        target_shares = item.get("目標股數", item["持有股數"])
        diff_shares = target_shares - item["持有股數"]
        
        if diff_shares > 0:
            action_str = f"🛒 買入 {diff_shares}"
            cash_flow = diff_shares * current_price if current_price else 0
            total_buy_cash += cash_flow
        elif diff_shares < 0:
            action_str = f"📉 賣出 {abs(diff_shares)}"
            cash_flow = abs(diff_shares) * current_price if current_price else 0
            total_sell_cash += cash_flow
        else:
            action_str = "✅ 已達標"
            
        total_cost += cost
        total_value += value
        
        portfolio_data.append({
            "群組": item["群組"], "代號": item["股票代號"], "名稱": item["股票名稱"], 
            "成本價": item["平均成本"], "現價": current_price if current_price else "無資料",
            "持有(股)": item["持有股數"], "目標(股)": target_shares, "動作": action_str, 
            "未實現損益": f"{int(profit):,}", "報酬率(%)": round(profit_percent, 2), "_raw_value": value 
        })

    col_data, col_chart = st.columns([1, 1])
    with col_data:
        st.markdown("#### 💰 總體績效與佈局計畫")
        c1, c2 = st.columns(2)
        c1.metric(f"{selected_filter} - 投入成本", f"${int(total_cost):,}")
        c2.metric(f"{selected_filter} - 目前市值", f"${int(total_value):,}")
        total_profit = total_value - total_cost
        total_profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else 0
        c3, c4 = st.columns(2)
        c3.metric(f"{selected_filter} - 未實現損益", f"${int(total_profit):,}", f"{round(total_profit_percent, 2)} %")
        c4.metric("🛒 預估需投入資金", f"${int(total_buy_cash):,}", delta_color="off")
        st.metric("💰 預估可收回現金 (減碼/賣出)", f"${int(total_sell_cash):,}", delta_color="normal")
        
    with col_chart:
        if total_value > 0:
            group_value_map = {}
            for item in portfolio_data:
                if item["_raw_value"] > 0:
                    grp = item["群組"]
                    group_value_map[grp] = group_value_map.get(grp, 0) + item["_raw_value"]
            pie_labels, pie_values = list(group_value_map.keys()), list(group_value_map.values())
            fig_pie = go.Figure(data=[go.Pie(labels=pie_labels, values=pie_values, hole=.4, textinfo='label+percent')])
            fig_pie.update_layout(title_text="🍰 資產配置 (依市值)", margin=dict(t=30, b=0, l=0, r=0), height=250)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("尚無現值資料可繪製圓餅圖")

    st.divider()
    if len(portfolio_data) > 0:
        df = pd.DataFrame(portfolio_data)
        st.markdown("### 📋 持股明細")
        st.table(df.drop(columns=["_raw_value"], errors='ignore').style.map(
            lambda x: 'color: red' if type(x) in [float, int] and x > 0 else ('color: green' if type(x) in [float, int] and x < 0 else ''), 
            subset=["報酬率(%)"]
        ))

# -------------------------------------------------------------------
# 🔥 全新分頁 B：自選股觀察池
# -------------------------------------------------------------------
elif page == "🌟 自選股觀察池":
    st.title("🌟 當沖與波段自選股池")
    st.markdown("將盤後做功課篩選出的潛力股存放在這裡，方便明天開盤時快速帶入各個環境評估面板！")
    
    with st.expander("➕ 新增自選股", expanded=False):
        w_ticker = st.text_input("股票代號", placeholder="例如: 2330")
        w_name = st.text_input("股票名稱", placeholder="例如: 台積電")
        w_note = st.text_input("操作備註", placeholder="例如: 爆量長紅，明天留意跳空開高作多")
        
        if st.button("加入自選池", type="primary"):
            if w_ticker and w_name:
                if w_ticker in [item["股票代號"] for item in st.session_state.watchlist]:
                    st.error("這檔股票已經在自選池囉！")
                else:
                    st.session_state.watchlist.append({
                        "股票代號": w_ticker.strip(), 
                        "股票名稱": w_name.strip(), 
                        "備註": w_note.strip()
                    })
                    try: update_watchlist_gsheets(st.session_state.watchlist)
                    except Exception as e: st.error(f"雲端存檔失敗: {e}")
                    st.success(f"{w_name} 已加入自選池！")
                    st.rerun()

    if len(st.session_state.watchlist) > 0:
        st.markdown("### 📋 目前觀察清單")
        watch_data = []
        for item in st.session_state.watchlist:
            hist, _ = fetch_stock_history(item["股票代號"], period="5d")
            price_str = "無資料"
            change_str = "-"
            
            if hist is not None and len(hist) >= 2:
                latest_close = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2]
                change_pct = ((latest_close - prev_close) / prev_close) * 100
                price_str = f"{round(latest_close, 2)}"
                change_str = f"{round(change_pct, 2)}%"
                if change_pct > 0: change_str = "🔺 " + change_str
                elif change_pct < 0: change_str = "🔻 " + change_str

            watch_data.append({
                "代號": item["股票代號"],
                "名稱": item["股票名稱"],
                "現價": price_str,
                "漲跌幅": change_str,
                "備註 (作戰計畫)": item.get("備註", "")
            })
            
        df_watch = pd.DataFrame(watch_data)
        st.table(df_watch)
        
        st.divider()
        st.markdown("#### 🗑️ 刪除自選股")
        del_options = [f"{item['股票代號']} {item['股票名稱']}" for item in st.session_state.watchlist]
        del_choice = st.selectbox("選擇要移除的股票", del_options)
        if st.button("從自選池移除"):
            del_ticker = del_choice.split(" ")[0]
            st.session_state.watchlist = [item for item in st.session_state.watchlist if item["股票代號"] != del_ticker]
            try: update_watchlist_gsheets(st.session_state.watchlist)
            except: pass
            st.success("移除成功！")
            st.rerun()
    else:
        st.info("目前自選池是空的，快去尋找潛力股加入吧！")

# -------------------------------------------------------------------
# 分頁 C：盤後籌碼主力追蹤 (加入自選股連動)
# -------------------------------------------------------------------
elif page == "🏦 盤後籌碼主力追蹤":
    st.title("🏦 盤後籌碼與主力追蹤")
    st.markdown("法人買、散戶賣，籌碼安定好發財！盤後 15:30 更新三大法人動向，20:00 更新融資融券餘額。")
    
    # 🔥 從自選股導入 UI
    wl_options = ["手動輸入代號..."] + [f"{item['股票代號']} {item['股票名稱']}" for item in st.session_state.get('watchlist', [])]
    wl_choice = st.selectbox("📂 從自選股快速帶入", wl_options)
    
    if wl_choice == "手動輸入代號...":
        chip_ticker = st.text_input("輸入要查詢的股票代號", value="2330", placeholder="例如: 2330")
    else:
        chip_ticker = wl_choice.split(" ")[0]
    
    if st.button("開始籌碼健檢", type="primary"):
        hist_data, actual_symbol = fetch_stock_history(chip_ticker, period="1mo")
        try:
            stock_info = yf.Ticker(actual_symbol).info
            stock_name = stock_info.get('shortName', chip_ticker)
        except:
            stock_name = chip_ticker
            
        latest_close = round(hist_data['Close'].iloc[-1], 2) if hist_data is not None else "無資料"
        st.markdown(f"### 🔍 【{stock_name}】籌碼日報 (現價: {latest_close})")
        
        inst_df = fetch_institutional(chip_ticker)
        margin_df = fetch_margin(chip_ticker)
        
        if not inst_df.empty:
            if not margin_df.empty: chip_df = inst_df.join(margin_df, how='left').fillna(0)
            else: chip_df = inst_df.copy()
            
            fig = go.Figure()
            if '外資' in chip_df.columns:
                fig.add_trace(go.Bar(x=chip_df.index, y=chip_df['外資'], name='外資', marker_color=chip_df['外資'].apply(lambda x: 'red' if x > 0 else 'green')))
            if '投信' in chip_df.columns:
                fig.add_trace(go.Bar(x=chip_df.index, y=chip_df['投信'], name='投信', marker_color=chip_df['投信'].apply(lambda x: 'darkred' if x > 0 else 'darkgreen')))
            fig.update_layout(title_text="📊 近 10 日外資與投信買賣超 (張數)", barmode='group', height=350, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### 🤖 系統籌碼綜合診斷")
            recent_3d = chip_df.head(3)
            sum_foreign = recent_3d['外資'].sum() if '外資' in recent_3d.columns else 0
            sum_trust = recent_3d['投信'].sum() if '投信' in recent_3d.columns else 0
            sum_margin = recent_3d['融資增減'].sum() if '融資增減' in recent_3d.columns else 0
            
            col1, col2, col3 = st.columns(3)
            col1.metric("近 3 日外資總計", f"{int(sum_foreign):,} 張", "買超偏多" if sum_foreign>0 else "賣超偏空", delta_color="normal" if sum_foreign>0 else "inverse")
            col2.metric("近 3 日投信總計", f"{int(sum_trust):,} 張", "買超偏多" if sum_trust>0 else "賣超偏空", delta_color="normal" if sum_trust>0 else "inverse")
            col3.metric("近 3 日融資總計 (散戶)", f"{int(sum_margin):,} 張", "散戶進場接刀" if sum_margin>0 else "散戶斷頭停損", delta_color="inverse" if sum_margin>0 else "normal")
            
            if sum_foreign > 0 and sum_trust > 0 and sum_margin < 0: st.success("🌟 **【完美籌碼 - 極度集中】**：外資與投信同步買超，且散戶融資大舉退場。籌碼完全落入大戶手中，非常容易拉升，強烈建議偏多操作！")
            elif (sum_foreign < 0 or sum_trust < 0) and sum_margin > 0: st.error("🚨 **【危險籌碼 - 散戶接刀】**：法人高檔倒貨，散戶不斷融資攤平。套牢賣壓重，強烈建議避開！")
            elif sum_trust > 0 and sum_foreign < 0: st.info("🟡 **【土洋對作 - 投信認養】**：外資賣、投信護盤。通常相對抗跌，觀察投信買超是否延續。")
            elif sum_foreign > 0 and sum_trust <= 0: st.info("🟡 **【外資單打獨鬥】**：靠外資買盤撐場，須留意隔日沖大戶(如美林、凱基台北)隔天的倒貨賣壓。")
            else: st.warning("📉 **【籌碼渙散】**：法人買盤並不積極，缺乏推升股價的燃料。")

            st.divider()
            st.markdown("#### 📋 籌碼流向明細表 (單位: 張)")
            st.dataframe(chip_df.style.map(lambda x: 'color: red' if type(x) in [float, int] and x > 0 else ('color: green' if type(x) in [float, int] and x < 0 else '')), use_container_width=True)
        else: st.error("找不到近期籌碼資料。")

# -------------------------------------------------------------------
# 分頁 D：當沖開盤環境評估 (加入自選股連動)
# -------------------------------------------------------------------
elif page == "⚡ 當沖開盤環境評估":
    st.title("⚡ 當沖開盤環境與股性評估")
    
    eval_mode = st.radio("請選擇評估模式：", 
                         ["🌙 盤前潛力評估 (前一交易日資料，適合 09:00 前使用)", 
                          "☀️ 開盤後動能評估 (今日即時資料，適合 09:15 後使用)"], 
                         horizontal=True)
    
    # 🔥 從自選股導入 UI
    wl_options = ["手動輸入代號..."] + [f"{item['股票代號']} {item['股票名稱']}" for item in st.session_state.get('watchlist', [])]
    wl_choice = st.selectbox("📂 從自選股快速帶入", wl_options)
    
    if wl_choice == "手動輸入代號...":
        dt_ticker = st.text_input("輸入要評估的股票代號", value="2330", placeholder="例如: 2330")
    else:
        dt_ticker = wl_choice.split(" ")[0]
    
    if st.button("開始評估", type="primary"):
        hist_data, actual_symbol = fetch_stock_history(dt_ticker, period="2mo")
        try:
            stock_info = yf.Ticker(actual_symbol).info
            stock_name = stock_info.get('shortName', dt_ticker)
        except: stock_name = dt_ticker
        
        if hist_data is not None and len(hist_data) >= 20:
            hist_data['MA5'] = hist_data['Close'].rolling(window=5).mean()
            hist_data['MA20'] = hist_data['Close'].rolling(window=20).mean()
            hist_data['H-L'] = hist_data['High'] - hist_data['Low']
            hist_data['H-PC'] = abs(hist_data['High'] - hist_data['Close'].shift(1))
            hist_data['L-PC'] = abs(hist_data['Low'] - hist_data['Close'].shift(1))
            hist_data['TR'] = hist_data[['H-L', 'H-PC', 'L-PC']].max(axis=1)
            hist_data['ATR_14'] = hist_data['TR'].rolling(14).mean()
            hist_data['Vol_5MA'] = hist_data['Volume'].rolling(5).mean()
            
            latest_ma5 = hist_data['MA5'].iloc[-1]
            latest_ma20 = hist_data['MA20'].iloc[-1]
            latest_atr = hist_data['ATR_14'].iloc[-1]
            latest_close = hist_data['Close'].iloc[-1]
            recent_10d_low = hist_data['Low'].tail(10).min()
            
            if latest_close > latest_ma20 and latest_ma5 > latest_ma20: entry_price = latest_ma5
            elif latest_close > latest_ma20 and latest_ma5 <= latest_ma20: entry_price = latest_ma20
            else: entry_price = latest_close
                
            atr_stop = entry_price - (1.5 * latest_atr)
            stop_loss_price = min(recent_10d_low, atr_stop) 
            if (entry_price - stop_loss_price) / entry_price > 0.1: stop_loss_price = entry_price * 0.90
            
            risk_per_share = entry_price - stop_loss_price
            take_profit_price = entry_price + (risk_per_share * 2)

            st.divider()
            st.markdown(f"### 🎯 【{stock_name}】關鍵操作點位參考")
            c_p, c_e, c_s, c_t = st.columns(4)
            c_p.metric("💰 最新股價", f"{round(latest_close, 2)}")
            c_e.metric("📍 適合進場價 (支撐)", f"{round(entry_price, 2)}")
            c_s.metric("🛡️ 嚴格停損價", f"{round(stop_loss_price, 2)}")
            c_t.metric("🎯 目標停利價", f"{round(take_profit_price, 2)}")
            st.divider()

            if "盤前" in eval_mode:
                st.markdown("### 🌙 盤前選股基因檢測")
                target_day = hist_data.iloc[-1]
                t_close, t_open, t_high, t_low, t_vol = target_day['Close'], target_day['Open'], target_day['High'], target_day['Low'], target_day['Volume']
                
                atr_pct = (target_day['ATR_14'] / t_close) * 100
                vol_ratio = t_vol / target_day['Vol_5MA'] if target_day['Vol_5MA'] > 0 else 1
                k_strength = (t_close - t_low) / (t_high - t_low) if t_high != t_low else 0.5

                col1, col2, col3 = st.columns(3)
                col1.metric("📊 股性活潑度 (ATR%)", f"{round(atr_pct, 2)} %", "大於 2.5% 才適合當沖", delta_color="normal" if atr_pct >= 2.5 else "inverse")
                col2.metric("💥 近期量能放大倍數", f"{round(vol_ratio, 1)} 倍", "🔥 爆量人氣股" if vol_ratio >= 1.5 else "平穩量", delta_color="normal" if vol_ratio >= 1.5 else "off")
                k_color = "normal" if k_strength >= 0.7 else ("inverse" if k_strength <= 0.3 else "off")
                col3.metric("📈 K線收盤位置", f"{round(k_strength*100, 1)} %", "強勢收高" if k_strength >= 0.7 else ("弱勢收低" if k_strength <= 0.3 else "長上影線/十字線"), delta_color=k_color)
                
                st.markdown("#### 🎯 盤前系統判定結果：")
                if atr_pct < 2.0: st.error("❌ **不適合放入自選池**：股性太過牛皮 (振幅 < 2%)，盤中波動極小，當沖極難獲利。")
                elif vol_ratio >= 1.5 and atr_pct >= 2.5 and k_strength >= 0.7: st.success("🔥 **極佳當沖獵物**：昨日爆量收高且股性活潑，今日極可能延續強勢！")
                elif atr_pct >= 2.5 and k_strength <= 0.3: st.warning("⚠️ **留意隔日沖倒貨賣壓**：股性活潑但留長上影線。早盤若開平低易有失望性賣壓，適合伺機做空。")
                else: st.info("🟡 **中性觀察標的**：股性尚可，需等開盤後實際動能表態。")

            else:
                st.markdown("### ☀️ 開盤後即時動能掃描")
                yesterday_data, today_data = hist_data.iloc[-2], hist_data.iloc[-1]
                y_close, t_open, t_current = yesterday_data['Close'], today_data['Open'], today_data['Close']
                
                gap_pct = ((t_open - y_close) / y_close) * 100
                atr_pct = (today_data['ATR_14'] / t_current) * 100
                intraday_pct = ((t_current - t_open)
