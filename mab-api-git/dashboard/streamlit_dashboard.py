# Multi-Armed Bandit Dashboard
# Execute este código no Streamlit in Snowflake

import streamlit as st
from snowflake.snowpark.context import get_active_session
import pandas as pd
import altair as alt
from datetime import datetime, timedelta

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
                WHEN m.impressions > 0 THEN (m.clicks / m.impressions) * 100
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
                WHEN impressions > 0 THEN (clicks / impressions) * 100
                ELSE 0 
            END AS ctr,
            clicks + 1 AS beta_alpha,
            impressions - clicks + 1 AS beta_beta
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
# Funções de Cálculo
# ===========================================

def calculate_thompson_allocation(df: pd.DataFrame, n_samples: int = 10000) -> pd.DataFrame:
    """Calcula alocação usando Thompson Sampling."""
    import numpy as np
    
    if df.empty:
        return df
    
    # Simular Thompson Sampling
    wins = {row['VARIANT_NAME']: 0 for _, row in df.iterrows()}
    
    for _ in range(n_samples):
        samples = {}
        for _, row in df.iterrows():
            alpha = int(row['BETA_ALPHA'])
            beta = int(row['BETA_BETA'])
            samples[row['VARIANT_NAME']] = np.random.beta(alpha, beta)
        
        winner = max(samples, key=samples.get)
        wins[winner] += 1
    
    # Calcular alocação
    df['allocation'] = df['VARIANT_NAME'].map(lambda x: round((wins[x] / n_samples) * 100, 1))
    
    # Calcular probabilidade de ser o melhor
    df['prob_best'] = df['allocation']
    
    return df


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
window_days = st.sidebar.slider("Janela de análise (dias)", 7, 30, 14)
chart_days = st.sidebar.slider("Dias no gráfico", 7, 90, 30)

# ===========================================
# Dados do Experimento
# ===========================================

# Carregar dados
variants_df = get_variants(selected_experiment_id)
metrics_df = get_daily_metrics(selected_experiment_id, chart_days)
allocation_df = get_allocation_data(selected_experiment_id, window_days)
summary_df = get_experiment_summary(selected_experiment_id)

# Calcular alocação
if not allocation_df.empty:
    allocation_df = calculate_thompson_allocation(allocation_df)

# ===========================================
# KPIs Principais
# ===========================================

st.header("📊 Resumo do Experimento")

col1, col2, col3, col4 = st.columns(4)

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

# ===========================================
# Alocação Atual
# ===========================================

st.header("🎯 Alocação Recomendada")

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
        st.dataframe(
            allocation_df[['VARIANT_NAME', 'CTR', 'allocation', 'prob_best']].rename(columns={
                'VARIANT_NAME': 'Variante',
                'CTR': 'CTR (%)',
                'allocation': 'Alocação (%)',
                'prob_best': 'Prob. Melhor (%)'
            }),
            hide_index=True
        )
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
        detailed_df = allocation_df[['VARIANT_NAME', 'IS_CONTROL', 'IMPRESSIONS', 'CLICKS', 'CTR', 'allocation']].copy()
        detailed_df.columns = ['Variante', 'Controle', 'Impressões', 'Clicks', 'CTR (%)', 'Alocação (%)']
        detailed_df['Controle'] = detailed_df['Controle'].map({True: '✅', False: '❌'})
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
    # Alerta: variante com poucas impressões
    for _, row in allocation_df.iterrows():
        if row['IMPRESSIONS'] < 1000:
            alerts.append(f"⚠️ **{row['VARIANT_NAME']}** tem poucas impressões ({int(row['IMPRESSIONS'])}). Resultados podem não ser confiáveis.")
    
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

if alerts:
    for alert in alerts:
        st.markdown(alert)
else:
    st.success("✅ Nenhum alerta no momento.")

# ===========================================
# Footer
# ===========================================

st.markdown("---")
st.markdown(
    f"*Última atualização: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}* | "
    f"*Janela de análise: {window_days} dias* | "
    f"*Algoritmo: Thompson Sampling*"
)

