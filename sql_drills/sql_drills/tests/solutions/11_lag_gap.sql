WITH gaps AS (
  SELECT user_name,
         LAG(login_on) OVER (PARTITION BY user_name ORDER BY login_on) AS prev_on,
         login_on
  FROM logins
)
SELECT user_name, prev_on, login_on, DATEDIFF(login_on, prev_on)
FROM gaps
WHERE DATEDIFF(login_on, prev_on) >= 7
ORDER BY user_name, login_on;
