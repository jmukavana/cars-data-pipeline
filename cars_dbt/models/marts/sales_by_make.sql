SELECT
    make,
    COUNT(*) AS sold_listings,
    COUNT(completed_sale_price) AS known_sale_prices,
    COUNT(*) - COUNT(completed_sale_price) AS missing_sale_prices,
    ROUND(AVG(completed_sale_price), 2) AS average_sale_price
FROM {{ ref('stg_car_listings') }}
WHERE sale_status = 'Sold'
GROUP BY make