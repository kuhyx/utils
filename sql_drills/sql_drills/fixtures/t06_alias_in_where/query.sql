SELECT customer_id, SUM(amount) AS total FROM orders WHERE total > 60 GROUP BY customer_id;
