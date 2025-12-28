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
        SELECT id, name, description, status, optimization_target, created_at
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
            m.sessions,
            m.impressions,
            m.clicks,
            m.revenue,
            CASE WHEN m.impressions > 0 THEN (CAST(m.clicks AS FLOAT) / m.impressions) * 100 ELSE 0 END AS ctr,
            CASE WHEN m.sessions > 0 THEN m.revenue / m.sessions ELSE 0 END AS rps,
            CASE WHEN m.impressions > 0 THEN (m.revenue / m.impressions) * 1000 ELSE 0 END AS rpm
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
                COALESCE(SUM(m.sessions), 0) AS sessions,
                COALESCE(SUM(m.impressions), 0) AS impressions,
                COALESCE(SUM(m.clicks), 0) AS clicks,
                COALESCE(SUM(m.revenue), 0) AS revenue
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
                CASE WHEN impressions > 0 THEN CAST(clicks AS FLOAT) / impressions ELSE 0 END AS ctr,
                CASE WHEN sessions > 0 THEN revenue / sessions ELSE 0 END AS rps,
                CASE WHEN impressions > 0 THEN (revenue / impressions) * 1000 ELSE 0 END AS rpm
            FROM aggregated
        )
        SELECT 
            variant_name,
            is_control,
            sessions,
            impressions,
            clicks,
            revenue,
            ctr,
            rps,
            rpm,
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
            SUM(m.sessions) AS total_sessions,
            SUM(m.impressions) AS total_impressions,
            SUM(m.clicks) AS total_clicks,
            SUM(m.revenue) AS total_revenue
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


def compute_normal_params_revenue(revenue: float, count: int) -> tuple:
    """
    Calcula parâmetros Normal para métricas de receita.
    """
    prior_mean = 0.01
    prior_variance = 0.01
    
    if count == 0:
        return prior_mean, np.sqrt(prior_variance)
    
    observed_mean = revenue / count
    posterior_mean = (prior_mean + observed_mean * count) / (1 + count)
    posterior_variance = prior_variance / (1 + count)
    
    return posterior_mean, np.sqrt(max(posterior_variance, 1e-10))


def calculate_thompson_allocation(df: pd.DataFrame, optimization_target: str = "ctr", n_samples: int = THOMPSON_SAMPLES) -> pd.DataFrame:
    """
    Calcula alocação usando Thompson Sampling.
    
    Suporta múltiplos targets:
    - ctr: Beta-Bernoulli
    - rps: Normal (revenue/sessions)
    - rpm: Normal (revenue/impressions * 1000)
    """
    if df.empty:
        return df
    
    wins = {row['VARIANT_NAME']: 0 for _, row in df.iterrows()}
    fallback_flags = {}
    
    # Preparar parâmetros por variante
    params = []
    for _, row in df.iterrows():
        impressions = int(row['IMPRESSIONS'])
        clicks = int(row['CLICKS'])
        sessions = int(row['SESSIONS'])
        revenue = float(row['REVENUE'])
        
        if optimization_target == "ctr":
            alpha, beta, is_fallback = compute_beta_params(clicks, impressions)
            params.append({
                'variant': row['VARIANT_NAME'],
                'type': 'beta',
                'alpha': alpha,
                'beta': beta
            })
            fallback_flags[row['VARIANT_NAME']] = is_fallback
        elif optimization_target == "rps":
            mean, std = compute_normal_params_revenue(revenue, sessions)
            params.append({
                'variant': row['VARIANT_NAME'],
                'type': 'normal',
                'mean': mean,
                'std': std
            })
            fallback_flags[row['VARIANT_NAME']] = sessions < MIN_IMPRESSIONS
        else:  # rpm
            mean, std = compute_normal_params_revenue(revenue * 1000, impressions)
            params.append({
                'variant': row['VARIANT_NAME'],
                'type': 'normal',
                'mean': mean,
                'std': std
            })
            fallback_flags[row['VARIANT_NAME']] = impressions < MIN_IMPRESSIONS
    
    # Simular Thompson Sampling
    for _ in range(n_samples):
        samples = {}
        for param in params:
            if param['type'] == 'beta':
                samples[param['variant']] = np.random.beta(param['alpha'], param['beta'])
            else:
                sample = np.random.normal(param['mean'], param['std'])
                samples[param['variant']] = max(0, sample)  # clip to non-negative
        
        winner = max(samples, key=samples.get)
        wins[winner] += 1
    
    # Calcular alocação
    df['allocation'] = df['VARIANT_NAME'].map(lambda x: round((wins[x] / n_samples) * 100, 1))
    df['prob_best'] = df['allocation']
    df['is_fallback'] = df['VARIANT_NAME'].map(fallback_flags)
    
    return df


def get_allocation_with_window_expansion(experiment_id: str) -> tuple:
    """
    Busca dados com expansão automática de janela.
    """
    df = get_allocation_data(experiment_id, DEFAULT_WINDOW_DAYS)
    window_used = DEFAULT_WINDOW_DAYS
    
    if not df.empty:
        min_impressions = df['IMPRESSIONS'].min()
        if min_impressions < MIN_IMPRESSIONS:
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

# Buscar optimization_target do experimento selecionado
selected_experiment = experiments_df[experiments_df['ID'] == selected_experiment_id].iloc[0]
optimization_target = selected_experiment.get('OPTIMIZATION_TARGET', 'ctr') or 'ctr'

# Configurações adicionais
chart_days = st.sidebar.slider("Dias no gráfico", 7, 90, 30)

# Mostrar configurações do algoritmo
st.sidebar.markdown("---")
st.sidebar.markdown("**Parâmetros do Algoritmo:**")
st.sidebar.markdown(f"- **Target:** {optimization_target.upper()}")
st.sidebar.markdown(f"- Prior: Beta({PRIOR_ALPHA}, {PRIOR_BETA})")
st.sidebar.markdown(f"- Min impressões: {MIN_IMPRESSIONS}")
st.sidebar.markdown(f"- Janela: {DEFAULT_WINDOW_DAYS}d → {MAX_WINDOW_DAYS}d")
st.sidebar.markdown(f"- Simulações: {THOMPSON_SAMPLES:,}")

# ===========================================
# Dados do Experimento
# ===========================================

variants_df = get_variants(selected_experiment_id)
metrics_df = get_daily_metrics(selected_experiment_id, chart_days)
allocation_df, window_used = get_allocation_with_window_expansion(selected_experiment_id)
summary_df = get_experiment_summary(selected_experiment_id)

# Calcular alocação
used_fallback = False
if not allocation_df.empty:
    allocation_df = calculate_thompson_allocation(allocation_df, optimization_target)
    used_fallback = allocation_df['is_fallback'].any()

# ===========================================
# KPIs Principais
# ===========================================

st.header("📊 Resumo do Experimento")

# Mostrar optimization target
target_labels = {"ctr": "CTR (Click-Through Rate)", "rps": "RPS (Revenue Per Session)", "rpm": "RPM (Revenue Per Mille)"}
st.info(f"🎯 **Otimizando:** {target_labels.get(optimization_target, optimization_target)}")

col1, col2, col3, col4, col5, col6 = st.columns(6)

if not summary_df.empty:
    summary = summary_df.iloc[0]
    
    with col1:
        st.metric(
            label="Sessions",
            value=f"{int(summary['TOTAL_SESSIONS']):,}" if summary['TOTAL_SESSIONS'] else "0"
        )
    
    with col2:
        st.metric(
            label="Impressões",
            value=f"{int(summary['TOTAL_IMPRESSIONS']):,}" if summary['TOTAL_IMPRESSIONS'] else "0"
        )
    
    with col3:
        st.metric(
            label="Clicks",
            value=f"{int(summary['TOTAL_CLICKS']):,}" if summary['TOTAL_CLICKS'] else "0"
        )
    
    with col4:
        st.metric(
            label="Receita",
            value=f"${float(summary['TOTAL_REVENUE']):,.2f}" if summary['TOTAL_REVENUE'] else "$0.00"
        )
    
    with col5:
        if optimization_target == "ctr":
            metric_value = (summary['TOTAL_CLICKS'] / summary['TOTAL_IMPRESSIONS'] * 100) if summary['TOTAL_IMPRESSIONS'] else 0
            st.metric(label="CTR Geral", value=f"{metric_value:.2f}%")
        elif optimization_target == "rps":
            metric_value = (summary['TOTAL_REVENUE'] / summary['TOTAL_SESSIONS']) if summary['TOTAL_SESSIONS'] else 0
            st.metric(label="RPS Geral", value=f"${metric_value:.4f}")
        else:  # rpm
            metric_value = (summary['TOTAL_REVENUE'] / summary['TOTAL_IMPRESSIONS'] * 1000) if summary['TOTAL_IMPRESSIONS'] else 0
            st.metric(label="RPM Geral", value=f"${metric_value:.2f}")
    
    with col6:
        st.metric(
            label="Janela",
            value=f"{window_used}d"
        )

# ===========================================
# Alocação Atual
# ===========================================

st.header("🎯 Alocação Recomendada")

if used_fallback:
    st.warning("⚠️ Algumas variantes têm dados insuficientes. Usando prior como fallback.")

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
            tooltip=['VARIANT_NAME', 'allocation', 'CTR', 'RPS', 'RPM', 'IMPRESSIONS', 'CLICKS', 'REVENUE']
        ).properties(
            height=200
        )
        st.altair_chart(allocation_chart, use_container_width=True)
    
    with col2:
        # Tabela de alocação com CI
        if optimization_target == "ctr":
            display_df = allocation_df[['VARIANT_NAME', 'CTR', 'CTR_CI_LOWER', 'CTR_CI_UPPER', 'allocation']].copy()
            display_df['CTR'] = display_df['CTR'].apply(lambda x: f"{x*100:.2f}%")
            display_df['IC 95%'] = display_df.apply(lambda r: f"[{r['CTR_CI_LOWER']*100:.2f}%, {r['CTR_CI_UPPER']*100:.2f}%]", axis=1)
            display_df = display_df[['VARIANT_NAME', 'CTR', 'IC 95%', 'allocation']]
            display_df.columns = ['Variante', 'CTR', 'IC 95%', 'Alocação (%)']
        elif optimization_target == "rps":
            display_df = allocation_df[['VARIANT_NAME', 'RPS', 'allocation']].copy()
            display_df['RPS'] = display_df['RPS'].apply(lambda x: f"${x:.4f}")
            display_df.columns = ['Variante', 'RPS', 'Alocação (%)']
        else:  # rpm
            display_df = allocation_df[['VARIANT_NAME', 'RPM', 'allocation']].copy()
            display_df['RPM'] = display_df['RPM'].apply(lambda x: f"${x:.2f}")
            display_df.columns = ['Variante', 'RPM', 'Alocação (%)']
        
        st.dataframe(display_df, hide_index=True)
else:
    st.info("Sem dados suficientes para calcular alocação.")

# ===========================================
# Evolução das Métricas
# ===========================================

st.header("📈 Evolução das Métricas")

if not metrics_df.empty:
    # Selecionar métrica para o gráfico
    metric_options = {"CTR (%)": "CTR", "RPS ($)": "RPS", "RPM ($)": "RPM"}
    default_index = 0
    if optimization_target == "rps":
        default_index = 1
    elif optimization_target == "rpm":
        default_index = 2
    
    selected_metric_label = st.selectbox("Métrica", list(metric_options.keys()), index=default_index)
    selected_metric = metric_options[selected_metric_label]
    
    # Gráfico de linha
    chart = alt.Chart(metrics_df).mark_line(point=True).encode(
        x=alt.X('METRIC_DATE:T', title='Data'),
        y=alt.Y(f'{selected_metric}:Q', title=selected_metric_label),
        color=alt.Color('VARIANT_NAME:N', title='Variante'),
        tooltip=['METRIC_DATE', 'VARIANT_NAME', 'CTR', 'RPS', 'RPM', 'SESSIONS', 'IMPRESSIONS', 'CLICKS', 'REVENUE']
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
    tab1, tab2, tab3 = st.tabs(["Sessions", "Impressões", "Receita"])
    
    with tab1:
        sessions_chart = alt.Chart(metrics_df).mark_bar().encode(
            x=alt.X('METRIC_DATE:T', title='Data'),
            y=alt.Y('SESSIONS:Q', title='Sessions'),
            color=alt.Color('VARIANT_NAME:N', title='Variante'),
            tooltip=['METRIC_DATE', 'VARIANT_NAME', 'SESSIONS']
        ).properties(height=300)
        st.altair_chart(sessions_chart, use_container_width=True)
    
    with tab2:
        impressions_chart = alt.Chart(metrics_df).mark_bar().encode(
            x=alt.X('METRIC_DATE:T', title='Data'),
            y=alt.Y('IMPRESSIONS:Q', title='Impressões'),
            color=alt.Color('VARIANT_NAME:N', title='Variante'),
            tooltip=['METRIC_DATE', 'VARIANT_NAME', 'IMPRESSIONS', 'CLICKS']
        ).properties(height=300)
        st.altair_chart(impressions_chart, use_container_width=True)
    
    with tab3:
        revenue_chart = alt.Chart(metrics_df).mark_bar().encode(
            x=alt.X('METRIC_DATE:T', title='Data'),
            y=alt.Y('REVENUE:Q', title='Receita ($)'),
            color=alt.Color('VARIANT_NAME:N', title='Variante'),
            tooltip=['METRIC_DATE', 'VARIANT_NAME', 'REVENUE']
        ).properties(height=300)
        st.altair_chart(revenue_chart, use_container_width=True)

# ===========================================
# Tabela Detalhada
# ===========================================

st.header("📋 Dados Detalhados")

tab1, tab2 = st.tabs(["Por Variante", "Por Dia"])

with tab1:
    if not allocation_df.empty:
        detailed_df = allocation_df[[
            'VARIANT_NAME', 'IS_CONTROL', 'SESSIONS', 'IMPRESSIONS', 'CLICKS', 'REVENUE',
            'CTR', 'CTR_CI_LOWER', 'CTR_CI_UPPER', 'RPS', 'RPM', 'allocation', 'is_fallback'
        ]].copy()
        
        detailed_df['CTR'] = detailed_df['CTR'].apply(lambda x: f"{x*100:.2f}%")
        detailed_df['IC 95%'] = detailed_df.apply(lambda r: f"[{r['CTR_CI_LOWER']*100:.2f}%, {r['CTR_CI_UPPER']*100:.2f}%]", axis=1)
        detailed_df['RPS'] = detailed_df['RPS'].apply(lambda x: f"${x:.4f}")
        detailed_df['RPM'] = detailed_df['RPM'].apply(lambda x: f"${x:.2f}")
        detailed_df['REVENUE'] = detailed_df['REVENUE'].apply(lambda x: f"${x:.2f}")
        detailed_df['IS_CONTROL'] = detailed_df['IS_CONTROL'].map({True: '✅', False: '❌'})
        detailed_df['is_fallback'] = detailed_df['is_fallback'].map({True: '⚠️', False: '✅'})
        
        detailed_df = detailed_df[[
            'VARIANT_NAME', 'IS_CONTROL', 'SESSIONS', 'IMPRESSIONS', 'CLICKS', 'REVENUE',
            'CTR', 'IC 95%', 'RPS', 'RPM', 'allocation', 'is_fallback'
        ]]
        detailed_df.columns = [
            'Variante', 'Controle', 'Sessions', 'Impressões', 'Clicks', 'Receita',
            'CTR', 'CTR IC 95%', 'RPS', 'RPM', 'Alocação (%)', 'Dados'
        ]
        st.dataframe(detailed_df, hide_index=True, use_container_width=True)

with tab2:
    if not metrics_df.empty:
        daily_df = metrics_df[[
            'METRIC_DATE', 'VARIANT_NAME', 'SESSIONS', 'IMPRESSIONS', 'CLICKS', 'REVENUE', 'CTR', 'RPS', 'RPM'
        ]].copy()
        daily_df['CTR'] = daily_df['CTR'].apply(lambda x: f"{x:.2f}%")
        daily_df['RPS'] = daily_df['RPS'].apply(lambda x: f"${x:.4f}")
        daily_df['RPM'] = daily_df['RPM'].apply(lambda x: f"${x:.2f}")
        daily_df['REVENUE'] = daily_df['REVENUE'].apply(lambda x: f"${x:.2f}")
        daily_df.columns = ['Data', 'Variante', 'Sessions', 'Impressões', 'Clicks', 'Receita', 'CTR', 'RPS', 'RPM']
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
    f"*Target: {optimization_target.upper()}* | "
    f"*Janela: {window_used} dias* | "
    f"*Algoritmo: {algorithm_status}*"
)
