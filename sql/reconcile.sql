WITH lines AS (
    SELECT count(*) AS accepted_lines, coalesce(sum(quantity), 0) AS line_units,
           coalesce(sum(quantity * price), 0) AS line_value_gbp
    FROM classified_lines JOIN selected_products USING (sku)
    WHERE exclusion_reason = 'accepted' AND date <= CAST(? AS DATE)
), daily AS (
    SELECT coalesce(sum(y), 0) AS daily_units FROM daily_sales JOIN selected_products USING (sku)
    WHERE date <= (SELECT max(date) - INTERVAL 1 DAY FROM source_lines)
)
SELECT * FROM lines CROSS JOIN daily;
