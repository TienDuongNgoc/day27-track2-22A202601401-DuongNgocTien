-- Protected model: Deduplicates active customers before joining to prevent
-- revenue inflation when customer dimension contains multiple active rows.

with completed_orders as (
    select *
    from {{ ref('stg_orders') }}
    where status = 'completed'
),
active_customers as (
    select distinct customer_id
    from {{ ref('stg_customers') }}
    where is_active = true
)
select
    o.order_date,
    count(*) as completed_order_rows,
    sum(o.amount_usd) as daily_revenue
from completed_orders o
left join active_customers c
    on o.customer_id = c.customer_id
group by 1
order by 1
