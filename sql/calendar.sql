-- No fabricated observations before a product's first actual positive sale.
SELECT p.sku, CAST(c.date AS DATE) AS date, coalesce(s.y, 0)::DOUBLE AS y
FROM selected_products p
CROSS JOIN LATERAL generate_series(CAST(p.first_sale AS DATE), CAST(? AS DATE), INTERVAL 1 DAY) c(date)
LEFT JOIN daily_sales s ON s.sku = p.sku AND s.date = c.date
ORDER BY p.sku, c.date;
