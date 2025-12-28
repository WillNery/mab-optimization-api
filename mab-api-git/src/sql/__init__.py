"""SQL queries for the MAB API."""


class ExperimentQueries:
    """SQL queries for experiments."""

    INSERT = """
        INSERT INTO experiments (id, name, description, status, optimization_target)
        VALUES (%(id)s, %(name)s, %(description)s, %(status)s, %(optimization_target)s)
    """

    SELECT_BY_ID = """
        SELECT id, name, description, status, optimization_target, created_at, updated_at
        FROM experiments
        WHERE id = %(id)s
    """

    SELECT_BY_NAME = """
        SELECT id, name, description, status, optimization_target, created_at, updated_at
        FROM experiments
        WHERE name = %(name)s
    """

    UPDATE_STATUS = """
        UPDATE experiments
        SET status = %(status)s, updated_at = CURRENT_TIMESTAMP()
        WHERE id = %(id)s
    """


class VariantQueries:
    """SQL queries for variants."""

    INSERT = """
        INSERT INTO variants (id, experiment_id, name, is_control)
        VALUES (%(id)s, %(experiment_id)s, %(name)s, %(is_control)s)
    """

    SELECT_BY_EXPERIMENT = """
        SELECT id, experiment_id, name, is_control, created_at
        FROM variants
        WHERE experiment_id = %(experiment_id)s
        ORDER BY is_control DESC, name
    """

    SELECT_BY_NAME_AND_EXPERIMENT = """
        SELECT id, experiment_id, name, is_control, created_at
        FROM variants
        WHERE experiment_id = %(experiment_id)s AND name = %(name)s
    """


class MetricsQueries:
    """SQL queries for metrics."""

    INSERT_RAW = """
        INSERT INTO raw_metrics (id, variant_id, metric_date, sessions, impressions, clicks, revenue, source, batch_id)
        VALUES (%(id)s, %(variant_id)s, %(metric_date)s, %(sessions)s, %(impressions)s, %(clicks)s, %(revenue)s, %(source)s, %(batch_id)s)
    """

    UPSERT_DAILY = """
        MERGE INTO daily_metrics AS target
        USING (
            SELECT 
                %(id)s AS id,
                %(variant_id)s AS variant_id,
                %(metric_date)s AS metric_date,
                %(sessions)s AS sessions,
                %(impressions)s AS impressions,
                %(clicks)s AS clicks,
                %(revenue)s AS revenue
        ) AS source
        ON target.variant_id = source.variant_id 
           AND target.metric_date = source.metric_date
        WHEN MATCHED THEN
            UPDATE SET 
                sessions = source.sessions,
                impressions = source.impressions,
                clicks = source.clicks,
                revenue = source.revenue,
                updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN
            INSERT (id, variant_id, metric_date, sessions, impressions, clicks, revenue)
            VALUES (source.id, source.variant_id, source.metric_date, source.sessions, source.impressions, source.clicks, source.revenue)
    """

    SELECT_FOR_ALLOCATION = """
        WITH aggregated AS (
            SELECT 
                v.id AS variant_id,
                v.name AS variant_name,
                v.is_control,
                COALESCE(SUM(m.sessions), 0) AS sessions,
                COALESCE(SUM(m.impressions), 0) AS impressions,
                COALESCE(SUM(m.clicks), 0) AS clicks,
                COALESCE(SUM(m.revenue), 0) AS revenue
            FROM variants v
            LEFT JOIN daily_metrics m 
                ON m.variant_id = v.id
                AND m.metric_date >= DATEADD(day, -%(window_days)s, CURRENT_DATE())
                AND m.metric_date < CURRENT_DATE()
            WHERE v.experiment_id = %(experiment_id)s
            GROUP BY v.id, v.name, v.is_control
        ),
        with_ctr AS (
            SELECT 
                *,
                CASE WHEN impressions > 0 THEN CAST(clicks AS FLOAT) / impressions ELSE 0 END AS ctr,
                CASE WHEN sessions > 0 THEN revenue / sessions ELSE 0 END AS rps,
                CASE WHEN impressions > 0 THEN (revenue / impressions) * 1000 ELSE 0 END AS rpm
            FROM aggregated
        )
        SELECT 
            variant_id,
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
        FROM with_ctr
        ORDER BY is_control DESC, variant_name
    """

    SELECT_HISTORY = """
        WITH with_ctr AS (
            SELECT 
                m.metric_date,
                v.id AS variant_id,
                v.name AS variant_name,
                v.is_control,
                m.sessions,
                m.impressions,
                m.clicks,
                m.revenue,
                CASE WHEN m.impressions > 0 THEN CAST(m.clicks AS FLOAT) / m.impressions ELSE 0 END AS ctr,
                CASE WHEN m.sessions > 0 THEN m.revenue / m.sessions ELSE 0 END AS rps,
                CASE WHEN m.impressions > 0 THEN (m.revenue / m.impressions) * 1000 ELSE 0 END AS rpm
            FROM daily_metrics m
            JOIN variants v ON v.id = m.variant_id
            WHERE v.experiment_id = %(experiment_id)s
        )
        SELECT 
            metric_date,
            variant_id,
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
        FROM with_ctr
        ORDER BY metric_date DESC, is_control DESC, variant_name
    """
