import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_gsheets import GSheetsConnection

# 網頁基本設定
st.set_page_config(page_title="台股持股監控面板", page_icon="", layout="wide")

# ==========================================
# 1. 建立 Google Sheets 連線與資料初始化
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def update_gsheets(data_list):
    new_df = pd.DataFrame(data_list)
    if not new_df.empty:
        new_df = new_df[["群組", "股票代號", "股票名稱", "持有股數", "平均成本", "目標股數"]]
    conn.update(worksheet="Portfolio", data=new_df)

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
    if "群組" not in item:
        item["群組"] = "其他"
    if "目標股數" not in item:
        item["目標股數"] = item.get("持有股數", 1000)

# ==========================================
# 2. 側邊欄 (Sidebar) - 分頁導覽
# ==========================================
st.sidebar.title("🧭 網站導覽")
page = st.sidebar.radio("選擇頁面", ["📊 個人持股監控", "😱 市場恐慌指數 (VIX)", "🔍 個股 K 線與進場分析"])
st.sidebar.divider()

@st.cache_data(ttl=60)
def fetch_stock_history(ticker, period="6mo"):
    try:
        stock = yf.Ticker(f"{ticker}.TW")
        hist = stock.history(period=period)
        if not hist.empty: return hist, f"{ticker}.TW"
        
        stock_otc = yf.Ticker(f"{ticker}.TWO")
        hist_otc = stock_otc.history(period=period)
        if not hist_otc.empty: return hist_otc, f"{ticker}.TWO"
    except Exception:
        pass
    return None, None

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
                        "股票名稱": new_name, "持有股數": new_shares, "平均成本": new_cost,
                        "目標股數": new_target
                    })
                    try: update_gsheets(st.session_state.portfolio)
                    except: pass
                    st.rerun()

    # --- 修改 / 刪除持股 ---
    with st.sidebar.expander("✏️ 修改 / 🗑️ 刪除持股", expanded=True):
        if len(st.session_state.portfolio) > 0:
            
            # 1. 背後選項清單：只存股票代號
            ticker_options = [item['股票代號'] for item in st.session_state.portfolio]
            
            # 2. 建立一個轉換函式：用代號去找出股票名稱來顯示
            def get_stock_name(ticker):
                for item in st.session_state.portfolio:
                    if item["股票代號"] == ticker:
                        name = item.get("股票名稱", "")
                        # 防呆：如果 Google 試算表名稱欄位空白 (NaN)，就顯示代號就好
                        if pd.isna(name) or str(name).strip() == "" or str(name).lower() == "nan":
                            return str(ticker)
                        return str(name)
                return str(ticker)

            # 3. 加上 format_func，這樣選單就只會顯示乾淨的「股票名稱」了！
            selected_ticker = st.selectbox("選擇要操作的股票", ticker_options, format_func=get_stock_name)
            
            current_item = next(item for item in st.session_state.portfolio if item["股票代號"] == selected_ticker)
            current_group = current_item.get("群組", "其他")
            
            edit_groups_list = combined_groups.copy()
            if current_group not in edit_groups_list and current_group != "➕ 自訂新群組...":
                edit_groups_list.insert(0, current_group)
                
            edit_group_choice = st.selectbox("更新群組分類", edit_groups_list, index=edit_groups_list.index(current_group) if current_group in edit_groups_list else 0)
            
            if edit_group_choice == "➕ 自訂新群組...":
                edit_group = st.text_input("請輸入自訂群組名稱", value=current_group)
            else:
                edit_group = edit_group_choice
                
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
    total_cost = total_value = 0
    total_buy_cash = 0  # 🔥 買進需投入資金
    total_sell_cash = 0 # 🔥 賣出可變現資金

    for item in filtered_portfolio:
        hist, _ = fetch_stock_history(item["股票代號"], period="1d")
        current_price = round(hist['Close'].iloc[-1], 2) if hist is not None else 0
        
        cost = item["平均成本"] * item["持有股數"]
        value = current_price * item["持有股數"] if current_price else 0
        profit = value - cost
        profit_percent = (profit / cost * 100) if cost > 0 else 0
        
        # 🔥 計算買賣差額邏輯
        target_shares = item.get("目標股數", item["持有股數"])
        diff_shares = target_shares - item["持有股數"]
        
        if diff_shares > 0:
            action_str = f"🛒 買入 {diff_shares}"
            cash_flow = diff_shares * current_price if current_price else 0
            total_buy_cash += cash_flow
            cash_str = f"投入 ${int(cash_flow):,}"
        elif diff_shares < 0:
            action_str = f"📉 賣出 {abs(diff_shares)}"
            cash_flow = abs(diff_shares) * current_price if current_price else 0
            total_sell_cash += cash_flow
            cash_str = f"收回 ${int(cash_flow):,}"
        else:
            action_str = "✅ 已達標"
            cash_str = "$0"
            
        total_cost += cost
        total_value += value
        
        portfolio_data.append({
            "群組": item["群組"], "代號": item["股票代號"], "名稱": item["股票名稱"], 
            "持有(股)": item["持有股數"], "目標(股)": target_shares, 
            "調整動作": action_str, "預估資金變動": cash_str,  # 🔥 新增這兩欄
            "均價": item["平均成本"], "現價": current_price if current_price else "無資料",
            "總成本": f"{int(cost):,}", "總現值": f"{int(value):,}", 
            "未實現損益": f"{int(profit):,}", "報酬率 (%)": round(profit_percent, 2),
            "_raw_value": value 
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
        
        # 🔥 新增：預估變現金額顯示
        st.metric("💰 預估可收回現金 (減碼/賣出)", f"${int(total_sell_cash):,}", delta_color="normal")
        
    with col_chart:
        if total_value > 0:
            group_value_map = {}
            for item in portfolio_data:
                if item["_raw_value"] > 0:
                    grp = item["群組"]
                    group_value_map[grp] = group_value_map.get(grp, 0) + item["_raw_value"]
            
            pie_labels = list(group_value_map.keys())
            pie_values = list(group_value_map.values())
            
            fig_pie = go.Figure(data=[go.Pie(
                labels=pie_labels, values=pie_values, hole=.4,
                textinfo='label+percent',
                marker=dict(colors=go.Figure().layout.template.layout.colorway)
            )])
            fig_pie.update_layout(title_text="🍰 產業群組資產配置 (依市值)", margin=dict(t=30, b=0, l=0, r=0), height=250)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("尚無現值資料可繪製圓餅圖")

    st.divider()
    
    if len(portfolio_data) > 0:
        df = pd.DataFrame(portfolio_data)
        df_display = df.drop(columns=["_raw_value"], errors='ignore')
        
        st.markdown("### 📋 持股與佈局明細")
        st.dataframe(
            df_display.style.map(
                lambda x: 'color: red' if type(x) in [float, int] and x > 0 else ('color: green' if type(x) in [float, int] and x < 0 else ''), 
                subset=["報酬率 (%)"]
            ), 
            width='stretch'
        )

# -------------------------------------------------------------------
# 分頁 B：市場恐慌指數 (VIX)
# -------------------------------------------------------------------
elif page == "😱 市場恐慌指數 (VIX)":
    st.title("😱 市場恐慌指數 (CBOE VIX)")
    st.markdown("VIX 指數反映了投資人對未來 30 天市場波動的預期。由於台股與美股高度連動，此指數常被用來判斷全球資金的避險與恐慌程度。")
    
    @st.cache_data(ttl=3600)
    def fetch_vix(): return yf.Ticker("^VIX").history(period="6mo")
    vix_data = fetch_vix()
    
    if not vix_data.empty:
        curr = round(vix_data['Close'].iloc[-1], 2)
        prev = round(vix_data['Close'].iloc[-2], 2)
        
        if curr < 15: status = "🟢 樂觀/貪婪 (低波動)"
        elif curr < 20: status = "🟡 正常波動 (平穩)"
        elif curr < 30: status = "🟠 恐慌加劇 (高波動)"
        else: status = "🔴 極度恐慌 (非理性拋售)"

        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric(label=f"當前 VIX 指數", value=curr, delta=round(curr-prev, 2), delta_color="inverse")
            st.subheader(f"{status}")
        with col2:
            st.info("""
            ### 📊 VIX 區間代表意義：
            * **🟢 低於 15 (樂觀/貪婪)**：市場情緒穩定，投資人風險偏好高。需留意股市是否過熱。
            * **🟡 15 ~ 20 (正常波動)**：典型的市場環境，處於正常的震盪整理。
            * **🟠 20 ~ 30 (恐慌加劇)**：市場波動顯著放大，投資人避險情緒升溫。
            * **🔴 高於 30 (極度恐慌)**：市場出現恐慌性拋售，通常發生在股災，也往往是「危機入市」絕佳買點。
            """)
            
        st.divider()
        st.markdown("### 📈 過去半年 VIX 走勢圖")
        st.line_chart(vix_data[['Close']].rename(columns={'Close': 'VIX 指數'}))

# -------------------------------------------------------------------
# 分頁 C：個股 K 線與進場分析
# -------------------------------------------------------------------
elif page == "🔍 個股 K 線與進場分析":
    st.title("🔍 個股技術分析與策略面板")
    
    col1, col2, col3 = st.columns([2, 1, 2])
    with col1: target_ticker = st.text_input("輸入股票代號", value="2330", placeholder="例如: 2330")
    with col2: period_option = st.selectbox("資料期間", ["3mo", "6mo", "1y", "2y"], index=1)
    with col3: selected_indicators = st.multiselect("📈 附加技術指標", ["MACD", "RSI"], default=["MACD", "RSI"])
    
    if target_ticker:
        hist_data, actual_symbol = fetch_stock_history(target_ticker, period=period_option)
        
        if hist_data is not None:
            hist_data['MA5'] = hist_data['Close'].rolling(window=5).mean()
            hist_data['MA20'] = hist_data['Close'].rolling(window=20).mean()
            
            latest_date = hist_data.index[-1].strftime("%Y-%m-%d")
            latest_open, latest_high, latest_low, latest_close = hist_data['Open'].iloc[-1], hist_data['High'].iloc[-1], hist_data['Low'].iloc[-1], hist_data['Close'].iloc[-1]
            latest_volume = int(hist_data['Volume'].iloc[-1])
            
            exp1 = hist_data['Close'].ewm(span=12, adjust=False).mean()
            exp2 = hist_data['Close'].ewm(span=26, adjust=False).mean()
            hist_data['MACD'] = exp1 - exp2
            hist_data['Signal'] = hist_data['MACD'].ewm(span=9, adjust=False).mean()
            hist_data['MACD_Hist'] = hist_data['MACD'] - hist_data['Signal']
            
            delta = hist_data['Close'].diff()
            up = delta.clip(lower=0)
            down = -1 * delta.clip(upper=0)
            ema_up = up.ewm(com=13, adjust=False).mean()
            ema_down = down.ewm(com=13, adjust=False).mean()
            rs = ema_up / ema_down
            hist_data['RSI'] = 100 - (100 / (1 + rs))
# === 新增：計算 ATR (14日真實波動幅度) ===
            hist_data['H-L'] = hist_data['High'] - hist_data['Low']
            hist_data['H-PC'] = abs(hist_data['High'] - hist_data['Close'].shift(1))
            hist_data['L-PC'] = abs(hist_data['Low'] - hist_data['Close'].shift(1))
            hist_data['TR'] = hist_data[['H-L', 'H-PC', 'L-PC']].max(axis=1)
            hist_data['ATR'] = hist_data['TR'].rolling(window=14).mean()
            latest_atr = hist_data['ATR'].iloc[-1]

            # --- 顯示最新日資訊 ---
            st.markdown(f"### 📅 最新交易日資訊 ({latest_date})")
            if len(hist_data) > 1:
                price_change = latest_close - hist_data['Close'].iloc[-2]
                price_change_pct = (price_change / hist_data['Close'].iloc[-2]) * 100
            else: price_change = price_change_pct = 0

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("開盤價", f"{latest_open:.2f}")
            m2.metric("最高價", f"{latest_high:.2f}")
            m3.metric("最低價", f"{latest_low:.2f}")
            m4.metric("收盤價", f"{latest_close:.2f}", f"{price_change:.2f} ({price_change_pct:.2f}%)", delta_color="inverse")
            m5.metric("成交量 (股)", f"{latest_volume:,}")
            st.divider()

            # --- 繪製圖表 ---
            num_rows = 2 + len(selected_indicators)
            row_heights = [0.5, 0.2]
            if len(selected_indicators) == 1: row_heights.append(0.3)
            elif len(selected_indicators) == 2: row_heights.extend([0.15, 0.15])

            fig = make_subplots(rows=num_rows, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=row_heights)
            
            fig.add_trace(go.Candlestick(x=hist_data.index, open=hist_data['Open'], high=hist_data['High'], low=hist_data['Low'], close=hist_data['Close'], name='K線', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
            fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['MA5'], line=dict(color='blue', width=1), name='MA5'), row=1, col=1)
            fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['MA20'], line=dict(color='orange', width=1), name='MA20'), row=1, col=1)
            
            colors = ['red' if row['Close'] >= row['Open'] else 'green' for _, row in hist_data.iterrows()]
            fig.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume'], marker_color=colors, name='成交量'), row=2, col=1)
            
            current_row = 3
            if "MACD" in selected_indicators:
                macd_colors = ['red' if val >= 0 else 'green' for val in hist_data['MACD_Hist']]
                fig.add_trace(go.Bar(x=hist_data.index, y=hist_data['MACD_Hist'], marker_color=macd_colors, name='MACD 柱狀圖'), row=current_row, col=1)
                fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['MACD'], line=dict(color='blue', width=1), name='MACD 線'), row=current_row, col=1)
                fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Signal'], line=dict(color='orange', width=1), name='Signal 線'), row=current_row, col=1)
                fig.update_yaxes(title_text="MACD", row=current_row, col=1)
                current_row += 1
                
            if "RSI" in selected_indicators:
                fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['RSI'], line=dict(color='purple', width=1.5), name='RSI (14)'), row=current_row, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="red", row=current_row, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="green", row=current_row, col=1)
                fig.update_yaxes(title_text="RSI", range=[0, 100], row=current_row, col=1)

            total_height = 600 if num_rows == 2 else 700 if num_rows == 3 else 800
            fig.update_layout(xaxis_rangeslider_visible=False, height=total_height, margin=dict(l=20, r=20, t=30, b=20), showlegend=False)
            fig.update_yaxes(title_text="股價", row=1, col=1)
            fig.update_yaxes(title_text="成交量", row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True)

            # ==========================================
            # 🔥 全新升級：策略計畫與邏輯核心
            # ==========================================
            st.markdown("### 🤖 系統技術面與進出場策略")
            
            if pd.isna(latest_ma20) or pd.isna(latest_atr):
                st.warning("資料量不足以計算技術指標，請選擇更長的期間。")
            else:
                # 1. 判斷趨勢狀態 (四象限)
                if latest_close > latest_ma20 and latest_ma5 > latest_ma20:
                    trend_status = "📈 **強勢多頭** (站上月線且短均線大於長均線)"
                    entry_advice = "多方控盤。建議在股價量縮回測 MA5 (週線) 或 MA20 (月線) 不破時，分批佈局進場。"
                elif latest_close > latest_ma20 and latest_ma5 <= latest_ma20:
                    trend_status = "🪀 **反彈震盪** (站上月線，但短線尚未完全轉強)"
                    entry_advice = "屬於築底反彈階段，可嘗試建立基本部位，並密切觀察 MA20 是否能確實守住轉為支撐。"
                elif latest_close <= latest_ma20 and latest_ma5 > latest_ma20:
                    trend_status = "⚠️ **短線轉弱** (跌破月線，但均線格局仍偏多)"
                    entry_advice = "跌破重要支撐！建議暫時觀望，確認是假跌破並重新站回 MA20 月線後，再考慮進場。"
                else:
                    trend_status = "📉 **弱勢空頭** (跌破月線且均線空頭排列)"
                    entry_advice = "目前長線趨勢向下，上檔套牢壓力沉重。強烈建議「不要進場接刀」，等待右側交易訊號(例如突破月線)。"

                st.info(f"**目前盤勢：** {trend_status}  \n**操作建議：** {entry_advice}")

                # 2. 計算動態進出場點位 (使用 ATR 波動率模型)
                recent_10d_low = hist_data['Low'].tail(10).min()
                atr_stop = latest_close - (1.5 * latest_atr) # 往下容忍 1.5 倍的日常波動
                
                # 取近10日低點與ATR動態低點中，較安全(較低)的那一個作為防守線
                stop_loss_price = min(recent_10d_low, atr_stop) 
                
                # 絕對防禦機制：不論波動多大，最大虧損不超過現價的 10%
                if (latest_close - stop_loss_price) / latest_close > 0.1: 
                    stop_loss_price = latest_close * 0.90
                
                # 算出預計承擔的風險金額
                risk_per_share = latest_close - stop_loss_price
                
                # 停利：風報比 1:2 (賺要賺賠的兩倍)
                take_profit_price = latest_close + (risk_per_share * 2)
                
                st.markdown("#### 🎯 動態波動防護模型 (風報比 1:2)")
                col_e, col_s, col_t = st.columns(3)
                
                col_e.metric("📍 預計進場價 (現價)", f"{round(latest_close, 2)}")
                
                sl_percent = ((stop_loss_price - latest_close) / latest_close) * 100
                col_s.metric("🛡️ 建議停損價 (動態防甩轎)", f"{round(stop_loss_price, 2)}", f"{round(sl_percent, 2)} %", delta_color="off")
                
                tp_percent = ((take_profit_price - latest_close) / latest_close) * 100
                col_t.metric("💰 目標停利價", f"{round(take_profit_price, 2)}", f"+{round(tp_percent, 2)} %", delta_color="normal")
                
                st.caption(f"💡 **策略邏輯說明**：系統計算出該檔股票近期的平均真實波動幅度 (ATR) 為 **{round(latest_atr, 2)}** 元。停損價設定為避開日常雜訊的「動態防守位置」並結合「近10日低點」，且強制將單筆最大虧損風險控制在 10% 以內。")
