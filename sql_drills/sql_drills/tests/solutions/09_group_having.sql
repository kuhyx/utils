SELECT team, COUNT(*), SUM(hours)
FROM tickets
WHERE priority <> 'low'
GROUP BY team
HAVING COUNT(*) >= 3 AND SUM(hours) >= 10
ORDER BY SUM(hours) DESC, team;
