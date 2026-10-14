-- Return mismatched months: dbt singular tests pass when no rows are returned.
WITH expected AS (
    SELECT
        DATE_TRUNC('month', sale_date)::date AS sale_month,
        COUNT(*) AS sold_listings,
        COUNT(completed_sale_price) AS known_sale_prices,
        COUNT(*) FILTER (WHERE completed_sale_price IS NULL) AS missing_sale_prices,
        SUM(completed_sale_price) AS recorded_sales_value
    FROM {{ ref('stg_car_listings') }}
    WHERE sale_status = 'Sold'
    GROUP BY 1
),
actual AS (
    SELECT *
    FROM {{ ref('monthly_sales') }}
)
SELECT
    expected.sale_month AS expected_sale_month,
    actual.sale_month AS actual_sale_month,
    expected.sold_listings AS expected_sold_listings,
    actual.sold_listings AS actual_sold_listings,
    expected.known_sale_prices AS expected_known_sale_prices,
    actual.known_sale_prices AS actual_known_sale_prices,
    expected.missing_sale_prices AS expected_missing_sale_prices,
    actual.missing_sale_prices AS actual_missing_sale_prices,
    expected.recorded_sales_value AS expected_recorded_sales_value,
    actual.recorded_sales_value AS actual_recorded_sales_value
FROM expected
FULL OUTER JOIN actual
    ON expected.sale_month = actual.sale_month
WHERE expected.sale_month IS NULL
   OR actual.sale_month IS NULL
   OR actual.sold_listings IS DISTINCT FROM expected.sold_listings
   OR actual.known_sale_prices IS DISTINCT FROM expected.known_sale_prices
   OR actual.missing_sale_prices IS DISTINCT FROM expected.missing_sale_prices
   OR actual.recorded_sales_value IS DISTINCT FROM expected.recorded_sales_value
