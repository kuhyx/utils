SELECT dept, name, salary, rnk
FROM (
  SELECT dept, name, salary,
         DENSE_RANK() OVER (PARTITION BY dept ORDER BY salary DESC) AS rnk
  FROM employees
) ranked
WHERE rnk <= 2
ORDER BY dept, rnk, name;
