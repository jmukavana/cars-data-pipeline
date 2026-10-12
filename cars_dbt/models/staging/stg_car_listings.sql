SELECT
    listing_id,
    vehicle_id,
    make,
    model,
    model_year,
    listing_price,
    odometer_km,
    sale_status,
    sale_date,
    completed_sale_price
FROM {{ source('cars_source', 'car_listings') }}