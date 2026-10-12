CREATE OR REPLACE VIEW vw_listing_mileage AS
SELECT
    f.listing_id,
    v.make,
    v.model,
    v.model_year,
    s.sale_status,
    f.odometer_km,
    CASE
        WHEN f.odometer_km < 50000 THEN 'Low mileage'
        WHEN f.odometer_km < 100000 THEN 'Medium mileage'
        ELSE 'High mileage'
    END AS mileage_category
FROM fact_car_listing AS f
JOIN dim_vehicle_model AS v
    ON v.vehicle_model_key = f.vehicle_model_key
JOIN dim_listing_status AS s
    ON s.status_key = f.status_key;



SELECT
    mileage_category,
    COUNT(*) AS listings,
    ROUND(AVG(odometer_km), 0) AS average_mileage_km
FROM vw_listing_mileage
GROUP BY mileage_category
ORDER BY average_mileage_km;


SELECT
    (SELECT COUNT(*) FROM fact_car_listing) AS fact_rows,
    (SELECT COUNT(*) FROM vw_listing_mileage) AS classified_rows;



GRANT SELECT ON public.vw_listing_mileage TO cars_reader;

SELECT *
FROM dbt_cars.sales_by_make
ORDER BY sold_listings DESC;
