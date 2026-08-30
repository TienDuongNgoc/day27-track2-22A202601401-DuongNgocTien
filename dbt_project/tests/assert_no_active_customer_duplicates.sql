-- Singular data test: Check that active customers dimension does not contain duplicate customer_ids
select
    customer_id,
    count(*) as active_record_count
from {{ ref('stg_customers') }}
where is_active = true
group by customer_id
having count(*) > 1
