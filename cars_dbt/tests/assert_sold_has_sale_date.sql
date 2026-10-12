SELECT
    listing_id,
    sale_status,
    sale_date
FROM {{ ref('stg_car_listings') }}
WHERE sale_status = 'Sold'
  AND sale_date IS NULL