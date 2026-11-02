SELECT customer, FORMAT(SUM(amount), 2), FORMAT(AVG(amount), 0)
FROM invoices
GROUP BY customer
ORDER BY SUM(amount) DESC;
