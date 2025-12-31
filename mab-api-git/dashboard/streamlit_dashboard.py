# Multi-Armed Bandit Dashboard
# Execute este código no Streamlit in Snowflake

import streamlit as st
from snowflake.snowpark.context import get_active_session
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import numpy as np

# ===========================================
# Configurações do Algoritmo (consistente com API)
# ===========================================
PRIOR_ALPHA = 1
PRIOR_BETA = 99
MIN_IMPRESSIONS = 10000
DEFAULT_WINDOW_DAYS = 14
MAX_WINDOW_DAYS = 30
THOMPSON_SAMPLES = 10000

# Configuração da página
st.set_page_config(
    page_title="MAB Dashboard",
    page_icon="🎰",
    layout="wide"
)

# Conexão com Snowflake
session = get_active_session()

# ===========================================
# Funções de Query
# ===========================================

@st.cache_data(ttl=60)
def get_experiments():
    """Busca todos os experimentos."""
    query = """
        SELECT id, name, description, status, created_at
        FROM activeview_mab.experiments.experiments
        ORDER BY created_at DESC
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=60)
def get_variants(experiment_id: str):
    """Busca variantes de um experimento."""
    query = f"""
        SELECT id, name, is_control
        FROM activeview_mab.experiments.variants
        WHERE experiment_id = '{experiment_id}'
        ORDER BY is_control DESC, name
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=60)
def get_daily_metrics(experiment_id: str, days: int = 30):
    """Busca métricas diárias de um experimento."""
    query = f"""
        SELECT 
            m.metric_date,
            v.name AS variant_name,
            v.is_control,
            m.impressions,
            m.clicks,
            CASE WHEN m.impressions > 0 THEN (CAST(m.clicks AS FLOAT) / m.impressions) * 100 ELSE 0 END AS ctr
        FROM activeview_mab.experiments.daily_metrics m
        JOIN activeview_mab.experiments.variants v ON v.id = m.variant_id
        WHERE v.experiment_id = '{experiment_id}'
          AND m.metric_date >= DATEADD(day, -{days}, CURRENT_DATE())
        ORDER BY m.metric_date, v.is_control DESC, v.name
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=60)
def get_allocation_data(experiment_id: str, window_days: int = 14):
    """Busca dados para cálculo de alocação com CI."""
    query = f"""
        WITH aggregated AS (
            SELECT 
                v.name AS variant_name,
                v.is_control,
                COALESCE(SUM(m.impressions), 0) AS impressions,
                COALESCE(SUM(m.clicks), 0) AS clicks
            FROM activeview_mab.experiments.variants v
            LEFT JOIN activeview_mab.experiments.daily_metrics m 
                ON m.variant_id = v.id
                AND m.metric_date >= DATEADD(day, -{window_days}, CURRENT_DATE())
                AND m.metric_date < CURRENT_DATE()
            WHERE v.experiment_id = '{experiment_id}'
            GROUP BY v.name, v.is_control
        ),
        with_metrics AS (
            SELECT 
                *,
                CASE WHEN impressions > 0 THEN CAST(clicks AS FLOAT) / impressions ELSE 0 END AS ctr
            FROM aggregated
        )
        SELECT 
            variant_name,
            is_control,
            impressions,
            clicks,
            ctr,
            -- CTR Confidence Interval 95% (Wilson Score)
            CASE 
                WHEN impressions > 0 THEN
                    (ctr + 1.92 / impressions - 1.96 * SQRT((ctr * (1 - ctr) + 0.96 / impressions) / impressions)) / (1 + 3.84 / impressions)
                ELSE 0 
            END AS ctr_ci_lower,
            CASE 
                WHEN impressions > 0 THEN
                    (ctr + 1.92 / impressions + 1.96 * SQRT((ctr * (1 - ctr) + 0.96 / impressions) / impressions)) / (1 + 3.84 / impressions)
                ELSE 0 
            END AS ctr_ci_upper
        FROM with_metrics
        ORDER BY is_control DESC, variant_name
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=60)
def get_experiment_summary(experiment_id: str):
    """Busca resumo do experimento."""
    query = f"""
        SELECT 
            COUNT(DISTINCT m.metric_date) AS days_with_data,
            MIN(m.metric_date) AS first_date,
            MAX(m.metric_date) AS last_date,
            SUM(m.impressions) AS total_impressions,
            SUM(m.clicks) AS total_clicks
        FROM activeview_mab.experiments.daily_metrics m
        JOIN activeview_mab.experiments.variants v ON v.id = m.variant_id
        WHERE v.experiment_id = '{experiment_id}'
    """
    return session.sql(query).to_pandas()


# ===========================================
# Funções de Cálculo (consistente com API)
# ===========================================

def compute_beta_params(clicks: int, impressions: int, use_fallback: bool = False) -> tuple:
    """
    Calcula parâmetros Beta usando Bayesian update.
    
    Prior: Beta(1, 99) → CTR esperado ~1%
    Posterior: Beta(α₀ + clicks, β₀ + impressions - clicks)
    """
    if use_fallback or impressions < MIN_IMPRESSIONS:
        return PRIOR_ALPHA, PRIOR_BETA, True
    
    alpha = PRIOR_ALPHA + clicks
    beta = PRIOR_BETA + impressions - clicks
    return alpha, beta, False


def calculate_thompson_allocation(df: pd.DataFrame, n_samples: int = THOMPSON_SAMPLES) -> pd.DataFrame:
    """
    Calcula alocação usando Thompson Sampling para CTR.
    
    Usa modelo Beta-Bernoulli para CTR.
    """
    if df.empty:
        return df
    
    wins = {row['VARIANT_NAME']: 0 for _, row in df.iterrows()}
    fallback_flags = {}
    
    # Compute beta parameters for each variant
    beta_params = {}
    for _, row in df.iterrows():
        name = row['VARIANT_NAME']
        impressions = int(row['IMPRESSIONS'])
        clicks = int(row['CLICKS'])
        
        alpha, beta, is_fallback = compute_beta_params(clicks, impressions)
        beta_params[name] = (alpha, beta)
        fallback_flags[name] = is_fallback
    
    # Monte Carlo simulation
    np.random.seed(42)  # For reproducibility in dashboard
    for _ in range(n_samples):
        samples = {}
        for name, (alpha, beta) in beta_params.items():
            samples[name] = np.random.beta(alpha, beta)
        
        winner = max(samples, key=samples.get)
        wins[winner] += 1
    
    # Convert wins to percentages
    df = df.copy()
    df['allocation'] = df['VARIANT_NAME'].map(lambda x: round(wins[x] / n_samples * 100, 1))
    df['is_fallback'] = df['VARIANT_NAME'].map(fallback_flags)
    
    return df


def check_data_sufficiency(df: pd.DataFrame, window_days: int) -> tuple:
    """
    Verifica se há dados suficientes e expande janela se necessário.
    
    Returns: (actual_window_days, used_fallback)
    """
    if df.empty:
        return MAX_WINDOW_DAYS, True
    
    min_impressions = df['IMPRESSIONS'].min()
    
    if min_impressions >= MIN_IMPRESSIONS:
        return window_days, False
    
    # Precisa expandir janela
    if window_days < MAX_WINDOW_DAYS:
        return MAX_WINDOW_DAYS, False
    
    # Mesmo com janela máxima, dados insuficientes
    return MAX_WINDOW_DAYS, True


# ===========================================
# Layout Principal
# ===========================================

st.title("🎰 Multi-Armed Bandit Dashboard")

# Sidebar
st.sidebar.header("Configurações")

# Selecionar experimento
experiments_df = get_experiments()

if experiments_df.empty:
    st.warning("Nenhum experimento encontrado.")
    st.stop()

experiment_options = {row['NAME']: row.to_dict() for _, row in experiments_df.iterrows()}
selected_name = st.sidebar.selectbox("Experimento", list(experiment_options.keys()))
selected_experiment = experiment_options[selected_name]
experiment_id = selected_experiment['ID']

# Janela temporal
window_days = st.sidebar.slider("Janela (dias)", 7, 30, DEFAULT_WINDOW_DAYS)

# Mostrar informações do experimento
st.sidebar.markdown("---")
st.sidebar.subheader("Info do Experimento")
st.sidebar.markdown(f"- **Status:** {selected_experiment['STATUS']}")
st.sidebar.markdown(f"- **Criado:** {selected_experiment['CREATED_AT']}")
st.sidebar.markdown(f"- **Target:** CTR")

# ===========================================
# Dados
# ===========================================

# Buscar dados
allocation_df = get_allocation_data(experiment_id, window_days)
metrics_df = get_daily_metrics(experiment_id, days=30)
summary_df = get_experiment_summary(experiment_id)

# Verificar suficiência de dados
window_used, used_fallback = check_data_sufficiency(allocation_df, window_days)

# Rebuscar com janela expandida se necessário
if window_used != window_days:
    allocation_df = get_allocation_data(experiment_id, window_used)

# Calcular alocação
if not allocation_df.empty:
    allocation_df = calculate_thompson_allocation(allocation_df)

# ===========================================
# Métricas Principais
# ===========================================

st.header("📊 Métricas Gerais")

if not summary_df.empty:
    summary = summary_df.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Dias com Dados", summary['DAYS_WITH_DATA'] or 0)
    with col2:
        st.metric("Total Impressões", f"{int(summary['TOTAL_IMPRESSIONS'] or 0):,}")
    with col3:
        st.metric("Total Clicks", f"{int(summary['TOTAL_CLICKS'] or 0):,}")
    with col4:
        total_ctr = (summary['TOTAL_CLICKS'] / summary['TOTAL_IMPRESSIONS'] * 100) if summary['TOTAL_IMPRESSIONS'] else 0
        st.metric("CTR Geral", f"{total_ctr:.2f}%")

# ===========================================
# Alocação Recomendada
# ===========================================

st.header("🎯 Alocação Recomendada")

if used_fallback:
    st.warning("⚠️ Algumas variantes têm dados insuficientes. Usando prior como fallback.")

st.info("🎯 **Otimizando:** CTR (Click-Through Rate)")

if not allocation_df.empty:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Gráfico de barras de alocação
        allocation_chart = alt.Chart(allocation_df).mark_bar().encode(
            x=alt.X('allocation:Q', title='Alocação (%)', scale=alt.Scale(domain=[0, 100])),
            y=alt.Y('VARIANT_NAME:N', title='Variante', sort='-x'),
            color=alt.Color('IS_CONTROL:N', 
                          scale=alt.Scale(domain=[True, False], range=['#1f77b4', '#ff7f0e']),
                          legend=alt.Legend(title='Controle')),
            tooltip=['VARIANT_NAME', 'allocation', 'CTR', 'IMPRESSIONS', 'CLICKS']
        ).properties(
            height=200
        )
        st.altair_chart(allocation_chart, use_container_width=True)
    
    with col2:
        # Tabela de alocação com CI
        display_df = allocation_df[['VARIANT_NAME', 'CTR', 'CTR_CI_LOWER', 'CTR_CI_UPPER', 'allocation']].copy()
        display_df['CTR'] = display_df['CTR'].apply(lambda x: f"{x*100:.2f}%")
        display_df['IC 95%'] = display_df.apply(lambda r: f"[{r['CTR_CI_LOWER']*100:.2f}%, {r['CTR_CI_UPPER']*100:.2f}%]", axis=1)
        display_df = display_df[['VARIANT_NAME', 'CTR', 'IC 95%', 'allocation']]
        display_df.columns = ['Variante', 'CTR', 'IC 95%', 'Alocação (%)']
        st.dataframe(display_df, hide_index=True)
else:
    st.info("Sem dados suficientes para calcular alocação.")

# ===========================================
# Evolução das Métricas
# ===========================================

st.header("📈 Evolução do CTR")

if not metrics_df.empty:
    # Gráfico de linha
    chart = alt.Chart(metrics_df).mark_line(point=True).encode(
        x=alt.X('METRIC_DATE:T', title='Data'),
        y=alt.Y('CTR:Q', title='CTR (%)'),
        color=alt.Color('VARIANT_NAME:N', title='Variante'),
        tooltip=['METRIC_DATE', 'VARIANT_NAME', 'CTR', 'IMPRESSIONS', 'CLICKS']
    ).properties(
        height=400
    )
    st.altair_chart(chart, use_container_width=True)
else:
    st.info("Sem dados de métricas para exibir.")

# ===========================================
# Volume
# ===========================================

st.header("📊 Volume por Dia")

if not metrics_df.empty:
    tab1, tab2 = st.tabs(["Impressões", "Clicks"])
    
    with tab1:
        impressions_chart = alt.Chart(metrics_df).mark_bar().encode(
            x=alt.X('METRIC_DATE:T', title='Data'),
            y=alt.Y('IMPRESSIONS:Q', title='Impressões'),
            color=alt.Color('VARIANT_NAME:N', title='Variante'),
            tooltip=['METRIC_DATE', 'VARIANT_NAME', 'IMPRESSIONS', 'CLICKS']
        ).properties(height=300)
        st.altair_chart(impressions_chart, use_container_width=True)
    
    with tab2:
        clicks_chart = alt.Chart(metrics_df).mark_bar().encode(
            x=alt.X('METRIC_DATE:T', title='Data'),
            y=alt.Y('CLICKS:Q', title='Clicks'),
            color=alt.Color('VARIANT_NAME:N', title='Variante'),
            tooltip=['METRIC_DATE', 'VARIANT_NAME', 'CLICKS']
        ).properties(height=300)
        st.altair_chart(clicks_chart, use_container_width=True)

# ===========================================
# Tabela Detalhada
# ===========================================

st.header("📋 Dados Detalhados")

tab1, tab2 = st.tabs(["Por Variante", "Por Dia"])

with tab1:
    if not allocation_df.empty:
        detailed_df = allocation_df[[
            'VARIANT_NAME', 'IS_CONTROL', 'IMPRESSIONS', 'CLICKS',
            'CTR', 'CTR_CI_LOWER', 'CTR_CI_UPPER', 'allocation', 'is_fallback'
        ]].copy()
        
        detailed_df['CTR'] = detailed_df['CTR'].apply(lambda x: f"{x*100:.2f}%")
        detailed_df['IC 95%'] = detailed_df.apply(lambda r: f"[{r['CTR_CI_LOWER']*100:.2f}%, {r['CTR_CI_UPPER']*100:.2f}%]", axis=1)
        detailed_df['IS_CONTROL'] = detailed_df['IS_CONTROL'].map({True: '✅', False: '❌'})
        detailed_df['is_fallback'] = detailed_df['is_fallback'].map({True: '⚠️', False: '✅'})
        
        detailed_df = detailed_df[[
            'VARIANT_NAME', 'IS_CONTROL', 'IMPRESSIONS', 'CLICKS',
            'CTR', 'IC 95%', 'allocation', 'is_fallback'
        ]]
        detailed_df.columns = [
            'Variante', 'Controle', 'Impressões', 'Clicks',
            'CTR', 'CTR IC 95%', 'Alocação (%)', 'Dados'
        ]
        st.dataframe(detailed_df, hide_index=True, use_container_width=True)

with tab2:
    if not metrics_df.empty:
        daily_df = metrics_df[[
            'METRIC_DATE', 'VARIANT_NAME', 'IMPRESSIONS', 'CLICKS', 'CTR'
        ]].copy()
        daily_df['CTR'] = daily_df['CTR'].apply(lambda x: f"{x:.2f}%")
        daily_df.columns = ['Data', 'Variante', 'Impressões', 'Clicks', 'CTR']
        st.dataframe(daily_df, hide_index=True, use_container_width=True)

# ===========================================
# Alertas
# ===========================================

st.header("⚠️ Alertas")

alerts = []

if not allocation_df.empty:
    for _, row in allocation_df.iterrows():
        if row['IMPRESSIONS'] < MIN_IMPRESSIONS:
            alerts.append(f"⚠️ **{row['VARIANT_NAME']}** tem apenas {int(row['IMPRESSIONS'])} impressões (mínimo: {MIN_IMPRESSIONS}). Usando fallback.")
    
    max_allocation = allocation_df['allocation'].max()
    if max_allocation > 95:
        winner = allocation_df[allocation_df['allocation'] == max_allocation]['VARIANT_NAME'].values[0]
        alerts.append(f"🏆 **{winner}** está dominando com {max_allocation}% de alocação. Considere encerrar o experimento.")

if not summary_df.empty:
    summary = summary_df.iloc[0]
    if summary['LAST_DATE']:
        last_date = pd.to_datetime(summary['LAST_DATE'])
        days_since_data = (datetime.now() - last_date).days
        if days_since_data > 2:
            alerts.append(f"📅 Último dado recebido há **{days_since_data} dias**. Verifique a ingestão.")

if window_used > DEFAULT_WINDOW_DAYS:
    alerts.append(f"📊 Janela expandida de {DEFAULT_WINDOW_DAYS} para {window_used} dias devido a dados insuficientes.")

if alerts:
    for alert in alerts:
        st.markdown(alert)
else:
    st.success("✅ Nenhum alerta no momento.")

# ===========================================
# Footer
# ===========================================

st.markdown("---")
algorithm_status = "Thompson Sampling (fallback)" if used_fallback else "Thompson Sampling"
st.markdown(
    f"*Última atualização: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}* | "
    f"*Target: CTR* | "
    f"*Janela: {window_used} dias* | "
    f"*Algoritmo: {algorithm_status}*"
)
