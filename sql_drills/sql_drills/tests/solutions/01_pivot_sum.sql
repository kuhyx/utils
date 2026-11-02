SELECT region,
       SUM(CASE WHEN quarter = 'Q1' THEN amount ELSE 0 END),
       SUM(CASE WHEN quarter = 'Q2' THEN amount ELSE 0 END),
       SUM(CASE WHEN quarter = 'Q3' THEN amount ELSE 0 END),
       SUM(CASE WHEN quarter = 'Q4' THEN amount ELSE 0 END)
FROM shop_sales
GROUP BY region
ORDER BY region;
