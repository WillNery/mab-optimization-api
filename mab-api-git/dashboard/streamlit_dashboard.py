# Multi-Armed Bandit Dashboard
# Execute este código no Streamlit in Snowflake

import streamlit as st
from snowflake.snowpark.context import get_active_session
import pandas as pd
import altair as alt
from datetime import datetime, timedelta

# ===========================================
# Configurações do Algoritmo (consistente com API)
# ===========================================
PRIOR_ALPHA = 1
PRIOR_BETA = 99
MIN_IMPRESSIONS = 200
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
            CASE 
                WHEN m.impressions > 0 THEN (CAST(m.clicks AS FLOAT) / m.impressions) * 100
                ELSE 0 
            END AS ctr
        FROM activeview_mab.experiments.daily_metrics m
        JOIN activeview_mab.experiments.variants v ON v.id = m.variant_id
        WHERE v.experiment_id = '{experiment_id}'
          AND m.metric_date >= DATEADD(day, -{days}, CURRENT_DATE())
        ORDER BY m.metric_date, v.is_control DESC, v.name
    """
    return session.sql(query).to_pandas()


@st.cache_data(ttl=60)
def get_allocation_data(experiment_id: str, window_days: int = 14):
    """Busca dados para cálculo de alocação."""
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
        )
        SELECT 
            variant_name,
            is_control,
            impressions,
            clicks,
            CASE 
                WHEN impressions > 0 THEN (CAST(clicks AS FLOAT) / impressions) * 100
                ELSE 0 
            END AS ctr
        FROM aggregated
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
    Calcula alocação usando Thompson Sampling.
    
    Consistente com a API:
    - Prior: Beta(1, 99)
    - Min impressions: 200
    - Fallback para prior se dados insuficientes
    """
    import numpy as np
    
    if df.empty:
        return df
    
    # Calcular parâmetros Beta para cada variante
    beta_params = []
    for _, row in df.iterrows():
        impressions = int(row['IMPRESSIONS'])
        clicks = int(row['CLICKS'])
        alpha, beta, is_fallback = compute_beta_params(clicks, impressions)
        beta_params.append({
            'variant': row['VARIANT_NAME'],
            'alpha': alpha,
            'beta': beta,
            'is_fallback': is_fallback
        })
    
    # Simular Thompson Sampling
    wins = {row['VARIANT_NAME']: 0 for _, row in df.iterrows()}
    
    for _ in range(n_samples):
        samples = {}
        for param in beta_params:
            samples[param['variant']] = np.random.beta(param['alpha'], param['beta'])
        
        winner = max(samples, key=samples.get)
        wins[winner] += 1
    
    # Calcular alocação
    df['allocation'] = df['VARIANT_NAME'].map(lambda x: round((wins[x] / n_samples) * 100, 1))
    
    # Calcular probabilidade de ser o melhor
    df['prob_best'] = df['allocation']
    
    # Adicionar flag de fallback
    fallback_map = {p['variant']: p['is_fallback'] for p in beta_params}
    df['is_fallback'] = df['VARIANT_NAME'].map(fallback_map)
    
    return df


def get_allocation_with_window_expansion(experiment_id: str) -> tuple:
    """
    Busca dados com expansão automática de janela.
    
    1. Tenta com 14 dias
    2. Se alguma variante tem < 200 impressões, expande para 30 dias
    3. Retorna dados e janela utilizada
    """
    # Tentar com janela padrão
    df = get_allocation_data(experiment_id, DEFAULT_WINDOW_DAYS)
    window_used = DEFAULT_WINDOW_DAYS
    
    # Verificar se precisa expandir
    if not df.empty:
        min_impressions = df['IMPRESSIONS'].min()
        if min_impressions < MIN_IMPRESSIONS:
            # Expandir para janela máxima
            df = get_allocation_data(experiment_id, MAX_WINDOW_DAYS)
            window_used = MAX_WINDOW_DAYS
    
    return df, window_used


# ===========================================
# Interface
# ===========================================

st.title("🎰 Multi-Armed Bandit Dashboard")
st.markdown("Acompanhamento de experimentos A/B com Thompson Sampling")

# Sidebar - Seleção de experimento
st.sidebar.header("Configurações")

experiments_df = get_experiments()

if experiments_df.empty:
    st.warning("Nenhum experimento encontrado. Crie um experimento via API primeiro.")
    st.stop()

experiment_options = dict(zip(experiments_df['NAME'], experiments_df['ID']))
selected_experiment_name = st.sidebar.selectbox(
    "Selecione o Experimento",
    options=list(experiment_options.keys())
)
selected_experiment_id = experiment_options[selected_experiment_name]

# Configurações adicionais
chart_days = st.sidebar.slider("Dias no gráfico", 7, 90, 30)

# Mostrar configurações do algoritmo
st.sidebar.markdown("---")
st.sidebar.markdown("**Parâmetros do Algoritmo:**")
st.sidebar.markdown(f"- Prior: Beta({PRIOR_ALPHA}, {PRIOR_BETA})")
st.sidebar.markdown(f"- Min impressões: {MIN_IMPRESSIONS}")
st.sidebar.markdown(f"- Janela: {DEFAULT_WINDOW_DAYS}d → {MAX_WINDOW_DAYS}d")
st.sidebar.markdown(f"- Simulações: {THOMPSON_SAMPLES:,}")

# ===========================================
# Dados do Experimento
# ===========================================

# Carregar dados
variants_df = get_variants(selected_experiment_id)
metrics_df = get_daily_metrics(selected_experiment_id, chart_days)
allocation_df, window_used = get_allocation_with_window_expansion(selected_experiment_id)
summary_df = get_experiment_summary(selected_experiment_id)

# Calcular alocação
used_fallback = False
if not allocation_df.empty:
    allocation_df = calculate_thompson_allocation(allocation_df)
    used_fallback = allocation_df['is_fallback'].any()

# ===========================================
# KPIs Principais
# ===========================================

st.header("📊 Resumo do Experimento")

col1, col2, col3, col4, col5 = st.columns(5)

if not summary_df.empty:
    summary = summary_df.iloc[0]
    
    with col1:
        st.metric(
            label="Total de Impressões",
            value=f"{int(summary['TOTAL_IMPRESSIONS']):,}" if summary['TOTAL_IMPRESSIONS'] else "0"
        )
    
    with col2:
        st.metric(
            label="Total de Clicks",
            value=f"{int(summary['TOTAL_CLICKS']):,}" if summary['TOTAL_CLICKS'] else "0"
        )
    
    with col3:
        ctr_geral = (summary['TOTAL_CLICKS'] / summary['TOTAL_IMPRESSIONS'] * 100) if summary['TOTAL_IMPRESSIONS'] else 0
        st.metric(
            label="CTR Geral",
            value=f"{ctr_geral:.2f}%"
        )
    
    with col4:
        st.metric(
            label="Dias com Dados",
            value=int(summary['DAYS_WITH_DATA']) if summary['DAYS_WITH_DATA'] else 0
        )
    
    with col5:
        st.metric(
            label="Janela Usada",
            value=f"{window_used} dias"
        )

# ===========================================
# Alocação Atual
# ===========================================

st.header("🎯 Alocação Recomendada")

# Mostrar se usou fallback
if used_fallback:
    st.warning("⚠️ Algumas variantes têm menos de 200 impressões. Usando prior como fallback.")

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
        # Tabela de alocação
        display_df = allocation_df[['VARIANT_NAME', 'CTR', 'allocation', 'prob_best', 'is_fallback']].copy()
        display_df['is_fallback'] = display_df['is_fallback'].map({True: '⚠️', False: '✅'})
        display_df = display_df.rename(columns={
            'VARIANT_NAME': 'Variante',
            'CTR': 'CTR (%)',
            'allocation': 'Alocação (%)',
            'prob_best': 'Prob. Melhor (%)',
            'is_fallback': 'Dados'
        })
        st.dataframe(display_df, hide_index=True)
else:
    st.info("Sem dados suficientes para calcular alocação.")

# ===========================================
# Evolução do CTR
# ===========================================

st.header("📈 Evolução do CTR")

if not metrics_df.empty:
    # Gráfico de linha
    ctr_chart = alt.Chart(metrics_df).mark_line(point=True).encode(
        x=alt.X('METRIC_DATE:T', title='Data'),
        y=alt.Y('CTR:Q', title='CTR (%)'),
        color=alt.Color('VARIANT_NAME:N', title='Variante'),
        tooltip=['METRIC_DATE', 'VARIANT_NAME', 'CTR', 'IMPRESSIONS', 'CLICKS']
    ).properties(
        height=400
    )
    st.altair_chart(ctr_chart, use_container_width=True)
else:
    st.info("Sem dados de métricas para exibir.")

# ===========================================
# Volume de Impressões
# ===========================================

st.header("📊 Volume de Impressões por Dia")

if not metrics_df.empty:
    impressions_chart = alt.Chart(metrics_df).mark_bar().encode(
        x=alt.X('METRIC_DATE:T', title='Data'),
        y=alt.Y('IMPRESSIONS:Q', title='Impressões'),
        color=alt.Color('VARIANT_NAME:N', title='Variante'),
        tooltip=['METRIC_DATE', 'VARIANT_NAME', 'IMPRESSIONS', 'CLICKS']
    ).properties(
        height=300
    )
    st.altair_chart(impressions_chart, use_container_width=True)

# ===========================================
# Tabela Detalhada
# ===========================================

st.header("📋 Dados Detalhados")

tab1, tab2 = st.tabs(["Por Variante", "Por Dia"])

with tab1:
    if not allocation_df.empty:
        detailed_df = allocation_df[['VARIANT_NAME', 'IS_CONTROL', 'IMPRESSIONS', 'CLICKS', 'CTR', 'allocation', 'is_fallback']].copy()
        detailed_df.columns = ['Variante', 'Controle', 'Impressões', 'Clicks', 'CTR (%)', 'Alocação (%)', 'Usando Fallback']
        detailed_df['Controle'] = detailed_df['Controle'].map({True: '✅', False: '❌'})
        detailed_df['Usando Fallback'] = detailed_df['Usando Fallback'].map({True: '⚠️ Sim', False: '✅ Não'})
        st.dataframe(detailed_df, hide_index=True, use_container_width=True)

with tab2:
    if not metrics_df.empty:
        daily_df = metrics_df[['METRIC_DATE', 'VARIANT_NAME', 'IMPRESSIONS', 'CLICKS', 'CTR']].copy()
        daily_df.columns = ['Data', 'Variante', 'Impressões', 'Clicks', 'CTR (%)']
        st.dataframe(daily_df, hide_index=True, use_container_width=True)

# ===========================================
# Alertas
# ===========================================

st.header("⚠️ Alertas")

alerts = []

if not allocation_df.empty:
    # Alerta: variante com poucas impressões (usando MIN_IMPRESSIONS)
    for _, row in allocation_df.iterrows():
        if row['IMPRESSIONS'] < MIN_IMPRESSIONS:
            alerts.append(f"⚠️ **{row['VARIANT_NAME']}** tem apenas {int(row['IMPRESSIONS'])} impressões (mínimo: {MIN_IMPRESSIONS}). Usando fallback (prior).")
    
    # Alerta: variante dominante
    max_allocation = allocation_df['allocation'].max()
    if max_allocation > 95:
        winner = allocation_df[allocation_df['allocation'] == max_allocation]['VARIANT_NAME'].values[0]
        alerts.append(f"🏆 **{winner}** está dominando com {max_allocation}% de alocação. Considere encerrar o experimento.")

if not summary_df.empty:
    summary = summary_df.iloc[0]
    # Alerta: sem dados recentes
    if summary['LAST_DATE']:
        last_date = pd.to_datetime(summary['LAST_DATE'])
        days_since_data = (datetime.now() - last_date).days
        if days_since_data > 2:
            alerts.append(f"📅 Último dado recebido há **{days_since_data} dias**. Verifique a ingestão.")

# Alerta: janela expandida
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
    f"*Janela: {window_used} dias* | "
    f"*Algoritmo: {algorithm_status}* | "
    f"*Prior: Beta({PRIOR_ALPHA}, {PRIOR_BETA})*"
)
