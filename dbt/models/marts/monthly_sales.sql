SELECT
    DATE_TRUNC('month', sale_date)::date AS sale_month,
    COUNT(*) AS sold_listings,
    COUNT(completed_sale_price) AS known_sale_prices,
    COUNT(*) - COUNT(completed_sale_price) AS missing_sale_prices,
    SUM(completed_sale_price) AS recorded_sales_value,
    ROUND(AVG(completed_sale_price), 2) AS average_sale_price,
    ROUND(
        100.0 * COUNT(completed_sale_price) / COUNT(*),
        2
    ) AS price_coverage_percent
FROM {{ ref('stg_car_listings') }}
WHERE sale_status = 'Sold'
GROUP BY 1