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
        INSERT INTO raw_metrics (id, variant_id, metric_date, impressions, clicks)
        VALUES (%(id)s, %(variant_id)s, %(metric_date)s, %(impressions)s, %(clicks)s)
    """

    UPSERT_DAILY = """
        MERGE INTO daily_metrics AS target
        USING (
            SELECT 
                %(id)s AS id,
                %(variant_id)s AS variant_id,
                %(metric_date)s AS metric_date,
                %(impressions)s AS impressions,
                %(clicks)s AS clicks
        ) AS source
        ON target.variant_id = source.variant_id 
           AND target.metric_date = source.metric_date
        WHEN MATCHED THEN
            UPDATE SET 
                impressions = source.impressions,
                clicks = source.clicks,
                updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN
            INSERT (id, variant_id, metric_date, impressions, clicks)
            VALUES (source.id, source.variant_id, source.metric_date, source.impressions, source.clicks)
    """

    SELECT_FOR_ALLOCATION = """
        WITH aggregated AS (
            SELECT 
                v.id AS variant_id,
                v.name AS variant_name,
                v.is_control,
                COALESCE(SUM(m.impressions), 0) AS impressions,
                COALESCE(SUM(m.clicks), 0) AS clicks
            FROM variants v
            LEFT JOIN daily_metrics m 
                ON m.variant_id = v.id
                AND m.metric_date >= DATEADD(day, -%(window_days)s, CURRENT_DATE())
                AND m.metric_date < CURRENT_DATE()
            WHERE v.experiment_id = %(experiment_id)s
            GROUP BY v.id, v.name, v.is_control
        )
        SELECT 
            variant_id,
            variant_name,
            is_control,
            impressions,
            clicks,
            CASE 
                WHEN impressions > 0 THEN clicks / impressions 
                ELSE 0 
            END AS ctr,
            clicks + %(prior_alpha)s AS beta_alpha,
            impressions - clicks + %(prior_beta)s AS beta_beta
        FROM aggregated
        ORDER BY is_control DESC, variant_name
    """

    SELECT_HISTORY = """
        SELECT 
            m.metric_date,
            v.id AS variant_id,
            v.name AS variant_name,
            v.is_control,
            m.impressions,
            m.clicks,
            CASE 
                WHEN m.impressions > 0 THEN m.clicks / m.impressions 
                ELSE 0 
            END AS ctr
        FROM daily_metrics m
        JOIN variants v ON v.id = m.variant_id
        WHERE v.experiment_id = %(experiment_id)s
        ORDER BY m.metric_date DESC, v.is_control DESC, v.name
    """


class AllocationHistoryQueries:
    """SQL queries for allocation history."""

    INSERT_HISTORY = """
        INSERT INTO allocation_history (
            id, experiment_id, computed_at, window_days, 
            algorithm, algorithm_version, seed, used_fallback,
            total_impressions, total_clicks
        )
        VALUES (
            %(id)s, %(experiment_id)s, %(computed_at)s, %(window_days)s,
            %(algorithm)s, %(algorithm_version)s, %(seed)s, %(used_fallback)s,
            %(total_impressions)s, %(total_clicks)s
        )
    """

    INSERT_DETAIL = """
        INSERT INTO allocation_history_details (
            id, allocation_history_id, variant_id, variant_name,
            is_control, allocation_percentage, impressions, clicks,
            ctr, beta_alpha, beta_beta
        )
        VALUES (
            %(id)s, %(allocation_history_id)s, %(variant_id)s, %(variant_name)s,
            %(is_control)s, %(allocation_percentage)s, %(impressions)s, %(clicks)s,
            %(ctr)s, %(beta_alpha)s, %(beta_beta)s
        )
    """

    SELECT_BY_EXPERIMENT = """
        SELECT 
            h.id,
            h.experiment_id,
            h.computed_at,
            h.window_days,
            h.algorithm,
            h.algorithm_version,
            h.seed,
            h.used_fallback,
            h.total_impressions,
            h.total_clicks
        FROM allocation_history h
        WHERE h.experiment_id = %(experiment_id)s
        ORDER BY h.computed_at DESC
        LIMIT %(limit)s
    """

    SELECT_DETAILS_BY_HISTORY = """
        SELECT 
            d.variant_id,
            d.variant_name,
            d.is_control,
            d.allocation_percentage,
            d.impressions,
            d.clicks,
            d.ctr,
            d.beta_alpha,
            d.beta_beta
        FROM allocation_history_details d
        WHERE d.allocation_history_id = %(allocation_history_id)s
        ORDER BY d.is_control DESC, d.allocation_percentage DESC
    """

    SELECT_BY_DATE = """
        SELECT 
            h.id,
            h.experiment_id,
            h.computed_at,
            h.window_days,
            h.algorithm,
            h.algorithm_version,
            h.seed,
            h.used_fallback,
            h.total_impressions,
            h.total_clicks
        FROM allocation_history h
        WHERE h.experiment_id = %(experiment_id)s
          AND DATE(h.computed_at) = %(target_date)s
        ORDER BY h.computed_at DESC
        LIMIT 1
    """
