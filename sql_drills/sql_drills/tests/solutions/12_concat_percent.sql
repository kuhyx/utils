SELECT poll_id,
       CONCAT(option_name, ': ',
              ROUND(100 * votes / SUM(votes) OVER (PARTITION BY poll_id), 1), '%')
FROM poll_votes
ORDER BY poll_id, votes DESC, option_name;
