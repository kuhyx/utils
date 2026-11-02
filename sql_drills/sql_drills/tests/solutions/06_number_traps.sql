SELECT team,
       ROUND(AVG(wins), 2),
       AVG(games),
       CAST(100 * SUM(wins) / SUM(games) AS DECIMAL(5, 1))
FROM team_results
GROUP BY team
ORDER BY team;
