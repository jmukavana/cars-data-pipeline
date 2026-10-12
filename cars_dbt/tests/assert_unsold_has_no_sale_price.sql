SELECT
    listing_id,
    sale_status,
    completed_sale_price
FROM {{ ref('stg_car_listings') }}
WHERE sale_status IS DISTINCT FROM 'Sold'
  AND completed_sale_price IS NOT NULL