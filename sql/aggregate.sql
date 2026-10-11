CREATE OR REPLACE TABLE daily_sales AS
SELECT sku, CAST(date AS DATE) AS date, sum(quantity)::DOUBLE AS y
FROM classified_lines
WHERE exclusion_reason = 'accepted'
GROUP BY sku, CAST(date AS DATE);
