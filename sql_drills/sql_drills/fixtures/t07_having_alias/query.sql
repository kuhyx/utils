SELECT customer_id, SUM(amount) AS total FROM orders GROUP BY customer_id HAVING total > 60 ORDER BY customer_id;
