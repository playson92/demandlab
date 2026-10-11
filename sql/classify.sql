-- First matching reason wins: mutually exclusive accounting buckets.
CREATE OR REPLACE TABLE classified_lines AS
SELECT source_lines.*,
    CASE
        WHEN country IS NULL OR country <> 'United Kingdom' THEN 'other_country'
        WHEN date IS NULL THEN 'invalid_date'
        WHEN sku IS NULL OR sku = '' THEN 'missing_sku'
        WHEN invoice IS NULL OR invoice = '' THEN 'missing_invoice'
        WHEN upper(invoice) LIKE 'C%' THEN 'cancellation'
        WHEN quantity IS NULL THEN 'invalid_quantity'
        WHEN quantity < 0 THEN 'negative_quantity_return_or_adjustment'
        WHEN quantity = 0 THEN 'zero_quantity'
        WHEN price IS NULL THEN 'invalid_price'
        WHEN price <= 0 THEN 'nonpositive_price'
        WHEN technical_rules.sku IS NOT NULL THEN 'technical_code'
        ELSE 'accepted'
    END AS exclusion_reason
FROM source_lines LEFT JOIN technical_rules USING (sku);
