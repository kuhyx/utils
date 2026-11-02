SELECT c.name, COALESCE(c.phone, 'n/a')
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id AND o.status <> 'cancelled'
WHERE o.id IS NULL
ORDER BY c.name;
