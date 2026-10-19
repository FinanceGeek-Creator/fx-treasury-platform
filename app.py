
import streamlit as st
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- Page Configuration & Professional Styling ---
st.set_page_config(
    page_title="Institutional Multi-Currency FX Structuring & Hedging Engine",
    layout="wide"
)

st.markdown("""
    <style>
    .main {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    h1, h2, h3 {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-weight: 600;
        color: #0F172A;
    }
    .stMetric {
        background-color: #F8FAFC;
        padding: 14px;
        border-radius: 8px;
        border: 1px solid #E2E8F0;
    }
    </style>
""", unsafe_allow_html=True)

st.title("Institutional Multi-Currency FX Hedging & Structuring Engine")
st.markdown("Advanced treasury platform supporting cross-currency pairs, volatility skew, CVA credit risk, Monte Carlo path simulation, and automated PDF pitch-books.")

# --- Sidebar Controls: Currency Pair Selection ---
st.sidebar.header("1. Currency Pair & Market Feed")
currency_pair = st.sidebar.selectbox(
    "Select Primary Currency Pair",
    ["USD/SGD", "EUR/SGD", "USD/JPY", "USD/CNY"]
)

pair_config = {
    "USD/SGD": {"ticker": "USDSGD=X", "base_curr": "SGD", "foreign_curr": "USD", "def_spot": 1.3100, "def_rd": 0.0320, "def_rf": 0.0450, "notional": 1000000},
    "EUR/SGD": {"ticker": "EURSGD=X", "base_curr": "SGD", "foreign_curr": "EUR", "def_spot": 1.4250, "def_rd": 0.0320, "def_rf": 0.0310, "notional": 1000000},
    "USD/JPY": {"ticker": "USDJPY=X", "base_curr": "JPY", "foreign_curr": "USD", "def_spot": 154.50, "def_rd": 0.0025, "def_rf": 0.0450, "notional": 150000000},
    "USD/CNY": {"ticker": "USDCNY=X", "base_curr": "CNY", "foreign_curr": "USD", "def_spot": 7.2300, "def_rd": 0.0210, "def_rf": 0.0450, "notional": 7500000}
}

cfg = pair_config[currency_pair]

@st.cache_data(ttl=300)
def fetch_live_market_data(ticker_symbol, fallback_rate):
    try:
        ticker = yf.Ticker(ticker_symbol)
        todays_data = ticker.history(period="1d")
        live_spot = float(todays_data['Close'].iloc[-1])
        return live_spot, True
    except Exception:
        return fallback_rate, False

live_spot_default, api_success = fetch_live_market_data(cfg["ticker"], cfg["def_spot"])

if api_success:
    st.sidebar.caption(f"Status: Live {currency_pair} Feed Connected")
else:
    st.sidebar.caption(f"Status: Using Offline Fallback Rate for {currency_pair}")

spot = st.sidebar.number_input(f"Spot {currency_pair}", value=round(live_spot_default, 4), step=0.0010 if live_spot_default < 10 else 0.05, format="%.4f" if live_spot_default < 10 else "%.2f")
baseline_vol = st.sidebar.slider("Baseline ATM Volatility", min_value=0.03, max_value=0.20, value=0.070, step=0.005)
t_maturity = st.sidebar.slider("Time to Maturity (Years)", min_value=0.25, max_value=2.0, value=1.0, step=0.25)

st.sidebar.header("2. Interest Rate Differentials")
r_domestic = st.sidebar.number_input(f"Domestic Rate ({cfg['base_curr']})", value=cfg["def_rd"], step=0.0010, format="%.4f")
r_foreign = st.sidebar.number_input(f"Foreign Rate ({cfg['foreign_curr']})", value=cfg["def_rf"], step=0.0010, format="%.4f")

st.sidebar.header("3. Strategy & Structuring Constraints")
structure_type = st.sidebar.selectbox(
    "Structuring Strategy", 
    ["Standard Zero-Cost Collar", "Seagull Spread (Upside Kicker)", "Knock-Out Barrier Collar", "Average-Rate Asian Collar"]
)

put_strike = st.sidebar.number_input(f"Target Floor Strike (Long Put) [{cfg['base_curr']}]", value=round(spot * 0.98, 4), step=0.0050 if spot < 10 else 0.10, format="%.4f" if spot < 10 else "%.2f")

if structure_type == "Seagull Spread (Upside Kicker)":
    upper_call_strike = st.sidebar.number_input(f"Upper Long Call Strike (Rally Kicker) [{cfg['base_curr']}]", value=round(spot * 1.08, 4), step=0.0050 if spot < 10 else 0.10, format="%.4f" if spot < 10 else "%.2f")
    barrier_level = None
elif structure_type == "Knock-Out Barrier Collar":
    upper_call_strike = st.sidebar.number_input(f"Cap Strike [{cfg['base_curr']}]", value=round(spot * 1.04, 4), step=0.0050 if spot < 10 else 0.10, format="%.4f" if spot < 10 else "%.2f")
    barrier_level = st.sidebar.number_input(f"Knock-Out Barrier Level (Upside) [{cfg['base_curr']}]", value=round(spot * 1.06, 4), step=0.0050 if spot < 10 else 0.10, format="%.4f" if spot < 10 else "%.2f")
else:
    upper_call_strike = st.sidebar.number_input(f"Cap Strike [{cfg['base_curr']}]", value=round(spot * 1.04, 4), step=0.0050 if spot < 10 else 0.10, format="%.4f" if spot < 10 else "%.2f")
    barrier_level = None

notional_usd = st.sidebar.number_input(f"Notional Amount ({cfg['foreign_curr']})", value=cfg["notional"], step=100000, format="%d")

st.sidebar.header("4. Counterparty Credit Parameters")
counterparty_rating = st.sidebar.selectbox("Counterparty Credit Rating", ["AAA", "A", "BBB", "BB"])

# --- Input Validation Guardrails ---
if put_strike >= spot:
    st.error("Validation Error: Target Floor Strike (Long Put) must be strictly below the Spot Reference rate for an exporter collar.")
    st.stop()

# --- Core Pricing & Skew Functions ---
def get_fx_skew_vol(strike: float, spot_ref: float, base_vol: float) -> float:
    moneyness = np.log(strike / spot_ref)
    skew_adjustment = -0.75 * moneyness + 0.45 * (moneyness ** 2)
    return max(0.02, base_vol + skew_adjustment)

def garman_kohlhagen_pricing(S, K, T, rd, rf, sigma, option_type):
    d1 = (np.log(S / K) + (rd - rf + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == 'call':
        price = S * np.exp(-rf * T) * norm.cdf(d1) - K * np.exp(-rd * T) * norm.cdf(d2)
        delta = np.exp(-rf * T) * norm.cdf(d1)
    elif option_type == 'put':
        price = K * np.exp(-rd * T) * norm.cdf(-d2) - S * np.exp(-rf * T) * norm.cdf(-d1)
        delta = -np.exp(-rf * T) * norm.cdf(-d1)
    
    gamma = (np.exp(-rf * T) * norm.pdf(d1)) / (S * sigma * np.sqrt(T))
    vega = S * np.exp(-rf * T) * norm.pdf(d1) * np.sqrt(T)
    
    return {"Price": price, "Delta": delta, "Gamma": gamma, "Vega": vega, "Volatility": sigma}

def calculate_cva(notional, rating, t_mat):
    pd_table = {"AAA": 0.0002, "A": 0.0010, "BBB": 0.0050, "BB": 0.0200}
    cumulative_pd = pd_table.get(rating, 0.0050) * t_mat
    lgd = 0.55  
    cva_charge = notional * lgd * cumulative_pd * 0.08
    return cva_charge

# --- Execution & Calculations for Primary Pair ---
put_vol = get_fx_skew_vol(put_strike, spot, baseline_vol)
put_result = garman_kohlhagen_pricing(spot, put_strike, t_maturity, r_domestic, r_foreign, put_vol, 'put')

solver_success = True
try:
    if structure_type in ["Standard Zero-Cost Collar", "Knock-Out Barrier Collar", "Average-Rate Asian Collar"]:
        def objective_call_strike(k_call):
            v_call = get_fx_skew_vol(k_call, spot, baseline_vol)
            c_res = garman_kohlhagen_pricing(spot, k_call, t_maturity, r_domestic, r_foreign, v_call, 'call')
            return c_res['Price'] - put_result['Price']
        
        optimal_call_strike = brentq(objective_call_strike, spot * 0.95, spot * 1.15)
        call_vol = get_fx_skew_vol(optimal_call_strike, spot, baseline_vol)
        call_result = garman_kohlhagen_pricing(spot, optimal_call_strike, t_maturity, r_domestic, r_foreign, call_vol, 'call')
        
        legs_data = [
            {"Leg": "Long Put (Floor)", "Strike": put_strike, "Implied Vol (%)": f"{put_vol*100:.2f}%", f"Unit Premium ({cfg['base_curr']})": put_result['Price'], "Delta": put_result['Delta'], "Gamma": put_result['Gamma'], "Vega": put_result['Vega']},
            {"Leg": "Short Call (Cap)", "Strike": optimal_call_strike, "Implied Vol (%)": f"{call_vol*100:.2f}%", f"Unit Premium ({cfg['base_curr']})": call_result['Price'], "Delta": call_result['Delta'], "Gamma": call_result['Gamma'], "Vega": call_result['Vega']}
        ]

    elif structure_type == "Seagull Spread (Upside Kicker)":
        uc_vol = get_fx_skew_vol(upper_call_strike, spot, baseline_vol)
        uc_result = garman_kohlhagen_pricing(spot, upper_call_strike, t_maturity, r_domestic, r_foreign, uc_vol, 'call')
        
        def objective_seagull_cap(k_call1):
            v_call1 = get_fx_skew_vol(k_call1, spot, baseline_vol)
            c1_res = garman_kohlhagen_pricing(spot, k_call1, t_maturity, r_domestic, r_foreign, v_call1, 'call')
            return c1_res['Price'] - (put_result['Price'] + uc_result['Price'])

        optimal_call_strike = brentq(objective_seagull_cap, spot * 0.95, spot * 1.05)
        call1_vol = get_fx_skew_vol(optimal_call_strike, spot, baseline_vol)
        call1_result = garman_kohlhagen_pricing(spot, optimal_call_strike, t_maturity, r_domestic, r_foreign, call1_vol, 'call')
        
        legs_data = [
            {"Leg": "Long Put (Floor)", "Strike": put_strike, "Implied Vol (%)": f"{put_vol*100:.2f}%", f"Unit Premium ({cfg['base_curr']})": put_result['Price'], "Delta": put_result['Delta'], "Gamma": put_result['Gamma'], "Vega": put_result['Vega']},
            {"Leg": "Short Call (Cap 1)", "Strike": optimal_call_strike, "Implied Vol (%)": f"{call1_vol*100:.2f}%", f"Unit Premium ({cfg['base_curr']})": call1_result['Price'], "Delta": call1_result['Delta'], "Gamma": call1_result['Gamma'], "Vega": call1_result['Vega']},
            {"Leg": "Long Call (Rally Kicker)", "Strike": upper_call_strike, "Implied Vol (%)": f"{uc_vol*100:.2f}%", f"Unit Premium ({cfg['base_curr']})": uc_result['Price'], "Delta": uc_result['Delta'], "Gamma": uc_result['Gamma'], "Vega": uc_result['Vega']}
        ]
except ValueError:
    solver_success = False

# --- Upgraded Institutional PDF Pitch-Book Generator ---
def generate_pdf_report(pair, strategy, spot_ref, floor_k, cap_k, notional, cva_val, base_curr):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, 
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    elements = []
    styles = getSampleStyleSheet()
    
    PRIMARY = colors.HexColor('#0F172A')    # Dark Slate / Navy
    SECONDARY = colors.HexColor('#0EA5E9')  # Vibrant Blue Accent
    TEXT_DARK = colors.HexColor('#1E293B')  # Charcoal Body
    BG_LIGHT = colors.HexColor('#F8FAFC')   # Soft Grey Fill
    BORDER_COLOR = colors.HexColor('#E2E8F0')

    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.white, fontName='Helvetica-Bold', spaceAfter=4)
    subtitle_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#94A3B8'), fontName='Helvetica')
    h2_style = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=12, textColor=PRIMARY, fontName='Helvetica-Bold', spaceBefore=12, spaceAfter=6)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=9, textColor=TEXT_DARK, leading=12)
    meta_label = ParagraphStyle('MetaLabel', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#64748B'), fontName='Helvetica-Bold')
    meta_val = ParagraphStyle('MetaVal', parent=styles['Normal'], fontSize=9, textColor=PRIMARY, fontName='Helvetica-Bold')

    # 1. Header Banner
    header_data = [
        [
            Paragraph("GLOBAL MARKETS &amp; TREASURY ADVISORY", subtitle_style),
            Paragraph("STRICTLY CONFIDENTIAL", ParagraphStyle('Conf', parent=subtitle_style, alignment=2))
        ],
        [
            Paragraph("FX DERIVATIVE STRUCTURING TERM SHEET", title_style),
            Paragraph("DATE: 19 OCT 2026", ParagraphStyle('Date', parent=subtitle_style, alignment=2, textColor=colors.white))
        ]
    ]
    header_table = Table(header_data, colWidths=[360, 180])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), PRIMARY),
        ('PADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 12))

    # 2. Executive Rationale & Summary
    elements.append(Paragraph("1. Executive Summary &amp; Strategy Overview", h2_style))
    summary_text = (
        f"This term sheet outlines the indicative pricing and structural terms for a <b>{strategy}</b> "
        f"denominated in <b>{pair}</b>. The primary objective is to establish an asymmetric hedge protecting "
        f"against adverse spot depreciations below <b>{floor_k:.4f}</b> while remaining zero-cost at inception "
        f"by capping upside participation at <b>{cap_k:.4f}</b>."
    )
    elements.append(Paragraph(summary_text, body_style))
    elements.append(Spacer(1, 10))

    # 3. Key Indicative Terms Table
    elements.append(Paragraph("2. Key Transaction Parameters", h2_style))
    terms_data = [
        [Paragraph("Structure Type", meta_label), Paragraph(strategy, meta_val), Paragraph("Currency Pair", meta_label), Paragraph(pair, meta_val)],
        [Paragraph("Spot Reference Rate", meta_label), Paragraph(f"{spot_ref:.4f}", meta_val), Paragraph("Notional Amount", meta_label), Paragraph(f"{pair.split('/')[0]} {notional:,.2f}", meta_val)],
        [Paragraph("Guaranteed Floor", meta_label), Paragraph(f"{floor_k:.4f}", meta_val), Paragraph("Primary Cap Strike", meta_label), Paragraph(f"{cap_k:.4f}", meta_val)],
        [Paragraph("Maturity Horizon", meta_label), Paragraph(f"{t_maturity} Year(s)", meta_val), Paragraph("Premium Parity", meta_label), Paragraph("Zero-Cost (Nil Premium)", meta_val)]
    ]
    terms_table = Table(terms_data, colWidths=[120, 150, 120, 150])
    terms_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(terms_table)
    elements.append(Spacer(1, 10))

    # 4. Credit & Exposure Callout Box
    elements.append(Paragraph("3. Counterparty Credit Risk &amp; CVA Metrics", h2_style))
    cva_data = [
        [
            Paragraph(f"<b>Estimated CVA Charge:</b> {base_curr} {cva_val:,.2f}", body_style),
            Paragraph(f"<b>Credit Rating Tier:</b> {counterparty_rating}", body_style)
        ],
        [
            Paragraph("<b>Risk Mitigation Note:</b> Credit Valuation Adjustment (CVA) reflects potential bilateral counterparty credit exposure over the trade lifecycle under Basel III framework standards.", ParagraphStyle('SubNote', parent=body_style, fontSize=8, textColor=colors.HexColor('#64748B')))
        ]
    ]
    cva_table = Table(cva_data, colWidths=[270, 270])
    cva_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F0F9FF')),
        ('BOX', (0,0), (-1,-1), 1, SECONDARY),
        ('PADDING', (0,0), (-1,-1), 8),
        ('SPAN', (0,1), (1,1)),
    ]))
    elements.append(cva_table)
    elements.append(Spacer(1, 15))

    # 5. Disclaimer / Footer
    disclaimer_text = (
        "<b>DISCLAIMER:</b> This document is indicative and for discussion purposes only. "
        "It does not constitute a binding commitment or offer to execute any derivative transaction. "
        "Final pricing is subject to live market conditions at the time of execution."
    )
    elements.append(Paragraph(disclaimer_text, ParagraphStyle('Disc', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#94A3B8'), leading=9)))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

# --- Dashboard Layout ---
if solver_success:
    cva_charge = calculate_cva(notional_usd, counterparty_rating, t_maturity)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Spot Reference", f"{spot:.4f}")
    col2.metric("Guaranteed Floor", f"{put_strike:.4f}", f"Floor Val: {cfg['base_curr']} {notional_usd * put_strike:,.0f}")
    col3.metric("Primary Cap Strike", f"{optimal_call_strike:.4f}", "Zero Premium Parity")
    col4.metric("Estimated CVA Charge", f"{cfg['base_curr']} {cva_charge:,.2f}", f"Rating: {counterparty_rating}")

    st.markdown("---")
    
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Multi-Currency Matrix",
        "Structure Details & Greeks", 
        "Payoff Profile", 
        "Monte Carlo Simulation",
        "Macro Stress-Test & PFE", 
        "Historical Backtest",
        "Client Pitch-Book PDF"
    ])
    
    with tab1:
        st.subheader("Batch Cross-Currency Structuring Matrix")
        st.markdown("Simultaneous comparison of standard zero-cost collar structures across all supported treasury pairs (assuming standard 2% OTM floor and 1-year maturity).")
        
        matrix_rows = []
        for p_name, p_conf in pair_config.items():
            p_spot, _ = fetch_live_market_data(p_conf["ticker"], p_conf["def_spot"])
            p_rd = p_conf["def_rd"]
            p_rf = p_conf["def_rf"]
            p_notional = p_conf["notional"]
            
            p_floor = round(p_spot * 0.98, 4)
            p_put_vol = get_fx_skew_vol(p_floor, p_spot, baseline_vol)
            p_put_res = garman_kohlhagen_pricing(p_spot, p_floor, t_maturity, p_rd, p_rf, p_put_vol, 'put')
            
            try:
                def obj_call(kc):
                    vc = get_fx_skew_vol(kc, p_spot, baseline_vol)
                    return garman_kohlhagen_pricing(p_spot, kc, t_maturity, p_rd, p_rf, vc, 'call')['Price'] - p_put_res['Price']
                
                p_cap = brentq(obj_call, p_spot * 0.95, p_spot * 1.15)
            except ValueError:
                p_cap = 0.0
                
            p_cva = calculate_cva(p_notional, counterparty_rating, t_maturity)
            
            matrix_rows.append({
                "Currency Pair": p_name,
                "Spot Rate": f"{p_spot:.4f}",
                "Floor Strike (-2%)": f"{p_floor:.4f}",
                "Parity Cap Strike": f"{p_cap:.4f}",
                f"CVA Charge ({p_conf['base_curr']})": f"{p_cva:,.2f}"
            })
            
        df_matrix = pd.DataFrame(matrix_rows)
        st.dataframe(df_matrix, use_container_width=True)

    with tab2:
        st.subheader(f"Structure Leg Breakdown ({currency_pair})")
        summary_df = pd.DataFrame(legs_data)
        for col_name in summary_df.columns:
            if "Unit Premium" in col_name:
                summary_df[col_name] = summary_df[col_name].apply(lambda x: f"{x:.5f}")
            elif col_name in ["Delta", "Gamma", "Vega"]:
                summary_df[col_name] = summary_df[col_name].apply(lambda x: f"{x:.4f}")
        st.table(summary_df)

    with tab3:
        st.subheader("Expiry Payoff Analysis (Hedged vs. Unhedged)")
        expiry_spots = np.linspace(spot * 0.80, spot * 1.20, 300)
        unhedged_payoff = expiry_spots * notional_usd
        
        if structure_type in ["Standard Zero-Cost Collar", "Knock-Out Barrier Collar", "Average-Rate Asian Collar"]:
            hedged_rate = np.where(expiry_spots < put_strike, put_strike, np.where(expiry_spots > optimal_call_strike, optimal_call_strike, expiry_spots))
        else:
            hedged_rate = np.piecewise(
                expiry_spots,
                [expiry_spots < put_strike, 
                 (expiry_spots >= put_strike) & (expiry_spots <= optimal_call_strike),
                 (expiry_spots > optimal_call_strike) & (expiry_spots <= upper_call_strike),
                 expiry_spots > upper_call_strike],
                [put_strike, lambda x: x, optimal_call_strike, lambda x: x - upper_call_strike + optimal_call_strike]
            )
            
        hedged_payoff = hedged_rate * notional_usd
        chart_df = pd.DataFrame({"Spot at Expiry": expiry_spots, f"Unhedged Conversion ({cfg['base_curr']})": unhedged_payoff, f"Hedged Strategy ({cfg['base_curr']})": hedged_payoff})
        
        fig = px.line(chart_df, x="Spot at Expiry", y=[f"Unhedged Conversion ({cfg['base_curr']})", f"Hedged Strategy ({cfg['base_curr']})"], title=f"Payoff Profile: {currency_pair} {structure_type}")
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.subheader("Monte Carlo Path-Dependent Simulation Engine")
        st.markdown("Simulating daily geometric Brownian motion paths with volatility skew to evaluate path-dependent pricing and barrier probabilities.")
        
        num_paths = st.slider("Number of Simulation Paths", min_value=500, max_value=5000, value=1000, step=500)
        num_steps = int(252 * t_maturity)
        dt = t_maturity / num_steps
        
        np.random.seed(101)
        z = np.random.standard_normal((num_paths, num_steps))
        sim_paths = np.zeros((num_paths, num_steps + 1))
        sim_paths[:, 0] = spot
        
        drift = (r_domestic - r_foreign - 0.5 * baseline_vol ** 2) * dt
        diffusion = baseline_vol * np.sqrt(dt)
        
        for t in range(1, num_steps + 1):
            sim_paths[:, t] = sim_paths[:, t - 1] * np.exp(drift + diffusion * z[:, t - 1])
            
        time_grid = np.linspace(0, t_maturity, num_steps + 1)
        
        fig_mc = go.Figure()
        for i in range(min(50, num_paths)):
            fig_mc.add_trace(go.Scatter(x=time_grid, y=sim_paths[i, :], mode='lines', line=dict(width=1, color='rgba(14, 165, 233, 0.2)'), showlegend=False))
            
        fig_mc.add_trace(go.Scatter(x=time_grid, y=np.mean(sim_paths, axis=0), mode='lines', line=dict(width=3, color='#0F172A'), name="Mean Path"))
        
        if structure_type == "Knock-Out Barrier Collar" and barrier_level:
            fig_mc.add_hline(y=barrier_level, line_dash="dash", line_color="red", annotation_text=f"Knock-Out Barrier: {barrier_level}")
            
        fig_mc.update_layout(title=f"Monte Carlo FX Simulation Paths ({currency_pair})", xaxis_title="Time (Years)", yaxis_title=f"Spot Rate ({currency_pair})")
        st.plotly_chart(fig_mc, use_container_width=True)
        
        final_spots = sim_paths[:, -1]
        mean_terminal = np.mean(final_spots)
        
        if structure_type == "Knock-Out Barrier Collar" and barrier_level:
            breached = np.any(sim_paths >= barrier_level, axis=1)
            knock_out_prob = np.mean(breached) * 100
            st.metric("Knock-Out Probability", f"{knock_out_prob:.1f}%", "Percentage of paths breaching barrier")
        elif structure_type == "Average-Rate Asian Collar":
            avg_spots = np.mean(sim_paths, axis=1)
            st.metric("Average Execution Rate (Asian)", f"{np.mean(avg_spots):.4f}", "Path-dependent arithmetic mean")
        
        st.metric("Monte Carlo Expected Terminal Spot", f"{mean_terminal:.4f}", f"Horizon: {t_maturity}Y")

    with tab5:
        st.subheader("Multi-Variable Stress Test & Credit Risk (PFE)")
        shock_scenarios = []
        for rate_shock in [-0.01, 0.0, 0.01]:
            for vol_shock in [-0.015, 0.0, 0.015]:
                s_rf = r_foreign + rate_shock
                s_rd = r_domestic + rate_shock
                s_p_vol = max(0.02, put_vol + vol_shock)
                s_c1_vol = max(0.02, call_vol + vol_shock)
                
                p_val = garman_kohlhagen_pricing(spot, put_strike, t_maturity, s_rd, s_rf, s_p_vol, 'put')['Price']
                c1_val = garman_kohlhagen_pricing(spot, optimal_call_strike, t_maturity, s_rd, s_rf, s_c1_vol, 'call')['Price']
                
                if structure_type == "Seagull Spread (Upside Kicker)":
                    s_uc_vol = max(0.02, uc_vol + vol_shock)
                    uc_val = garman_kohlhagen_pricing(spot, upper_call_strike, t_maturity, s_rd, s_rf, s_uc_vol, 'call')['Price']
                    net_mtm = round((c1_val - p_val - uc_val) * notional_usd, 2)
                else:
                    net_mtm = round((c1_val - p_val) * notional_usd, 2)
                
                shock_scenarios.append({
                    "Rate Shift (bps)": int(rate_shock * 10000),
                    "Vol Shift (%)": f"{vol_shock * 100:+.1f}%",
                    f"Net Structure MTM ({cfg['base_curr']})": net_mtm
                })
        
        df_stress = pd.DataFrame(shock_scenarios)
        max_pfe = abs(df_stress[f"Net Structure MTM ({cfg['base_curr']})"].min())
        st.metric("Estimated Max Potential Future Exposure (PFE)", f"{cfg['base_curr']} {max_pfe:,.2f}", "Worst-Case Stress MTM")
        st.dataframe(df_stress, use_container_width=True)

        csv_data = df_stress.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Stress-Test Report (CSV)",
            data=csv_data,
            file_name="fx_structure_stress_test.csv",
            mime="text/csv"
        )

    with tab6:
        st.subheader("Historical Backtesting (Rolling Simulation)")
        np.random.seed(42)
        dates = pd.date_range(start="2023-01-01", periods=250, freq="B")
        historical_spots = spot + np.cumsum(np.random.normal(0, spot * 0.002, 250))
        hist_df = pd.DataFrame({"Date": dates, "Historical Spot": historical_spots})
        
        if structure_type in ["Standard Zero-Cost Collar", "Knock-Out Barrier Collar", "Average-Rate Asian Collar"]:
            hist_hedged_rate = np.where(hist_df["Historical Spot"] < put_strike, put_strike, 
                                        np.where(hist_df["Historical Spot"] > optimal_call_strike, optimal_call_strike, hist_df["Historical Spot"]))
        else:
            hist_hedged_rate = np.piecewise(
                hist_df["Historical Spot"].values,
                [hist_df["Historical Spot"] < put_strike, 
                 (hist_df["Historical Spot"] >= put_strike) & (hist_df["Historical Spot"] <= optimal_call_strike),
                 (hist_df["Historical Spot"] > optimal_call_strike) & (hist_df["Historical Spot"] <= upper_call_strike),
                 hist_df["Historical Spot"] > upper_call_strike],
                [put_strike, lambda x: x, optimal_call_strike, lambda x: x - upper_call_strike + optimal_call_strike]
            )
            
        hist_df[f"Unhedged Conversion ({cfg['base_curr']})"] = hist_df["Historical Spot"] * notional_usd
        hist_df[f"Hedged Strategy ({cfg['base_curr']})"] = hist_hedged_rate * notional_usd

        fig_hist = px.line(
            hist_df, x="Date", y=[f"Unhedged Conversion ({cfg['base_curr']})", f"Hedged Strategy ({cfg['base_curr']})"], 
            title=f"Rolling Historical Backtest Performance ({currency_pair})",
            color_discrete_map={f"Unhedged Conversion ({cfg['base_curr']})": "#94A3B8", f"Hedged Strategy ({cfg['base_curr']})": "#0EA5E9"}
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    with tab7:
        st.subheader("Automated Client Pitch-Book Generation")
        st.markdown("Compile trade terms, structural pricing breakdowns, and credit adjustment charges into an institutional PDF memo.")
        
        pdf_bytes = generate_pdf_report(currency_pair, structure_type, spot, put_strike, optimal_call_strike, notional_usd, cva_charge, cfg['base_curr'])
        
        st.download_button(
            label="Download Client Pitch-Book (PDF)",
            data=pdf_bytes,
            file_name="fx_structuring_memo.pdf",
            mime="application/pdf"
        )
else:
    st.error("Root solver could not find a valid zero-cost parity strike within the specified range. Adjust market parameters or strike constraints.")