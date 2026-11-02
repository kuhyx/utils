SELECT DATE_FORMAT(order_date, '%Y-%m') AS month,
       COUNT(*),
       SUM(CASE WHEN status = 'shipped' THEN 1 ELSE 0 END),
       SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END),
       SUM(CASE WHEN status = 'shipped' THEN total ELSE 0 END)
FROM orders
GROUP BY month
ORDER BY month;
