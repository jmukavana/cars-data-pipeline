
-- Create a sales summary view
create  or replace  view  vw_sales_by_make as
select
    v.make,
    count(*) as sold_listings,
    count(f.completed_sale_price) as known_sale_prices,
    count(*) FILTER (
        WHERE f.completed_sale_price is null
        ) as missing_sales_prices,
    round(
    100.0* count(f.completed_sale_price) /
    nullif(count(*),0),2) as price_completeness_percent,
    round(avg(f.completed_sale_price),2) as average_recorded_sale_price
from fact_car_listing as f
join dim_vehicle_model as v
on v.vehicle_model_key = f.vehicle_model_key
join dim_listing_status as s
on s.status_key=f.status_key
where s.sale_status = 'Sold'
group by v.make;


SELECT *
FROM vw_sales_by_make
ORDER BY sold_listings DESC;

-- Create a monthly sales view

CREATE OR REPLACE VIEW vw_monthly_sales AS
SELECT
    DATE_TRUNC('month', f.sale_date)::date AS sale_month,
    COUNT(*) AS sold_listings,
    COUNT(f.completed_sale_price) AS known_sale_prices,
    ROUND(
        AVG(f.completed_sale_price),
        2
    ) AS average_recorded_sale_price
FROM fact_car_listing AS f
JOIN dim_listing_status AS s
    ON s.status_key = f.status_key
WHERE s.sale_status = 'Sold'
  AND f.sale_date IS NOT NULL
GROUP BY DATE_TRUNC('month', f.sale_date)::date;


SELECT *
FROM vw_monthly_sales
ORDER BY sale_month;

-- Reconcile the report

SELECT
    SUM(sold_listings) AS total_sold,
    SUM(known_sale_prices) AS known_prices,
    SUM(missing_sales_prices) AS missing_prices
FROM vw_sales_by_make;


SELECT ROUND(AVG(f.completed_sale_price), 2) AS overall_average
FROM fact_car_listing AS f
JOIN dim_listing_status AS s
    ON s.status_key = f.status_key
WHERE s.sale_status = 'Sold';


CREATE TABLE IF NOT EXISTS pipeline_batches (
    batch_id UUID PRIMARY KEY,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_rows BIGINT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    failed_step TEXT
);


SELECT
    batch_id,
    source_file,
    source_rows,
    status,
    failed_step,
    started_at,
    finished_at,
    finished_at - started_at AS duration
FROM pipeline_batches
ORDER BY started_at DESC
LIMIT 10;

SELECT
    source_sha256,
    COUNT(*) AS successful_runs,
    MAX(finished_at) AS last_success
FROM pipeline_batches
WHERE status = 'SUCCESS'
GROUP BY source_sha256
ORDER BY last_success DESC;