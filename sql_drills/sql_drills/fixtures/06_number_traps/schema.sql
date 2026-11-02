CREATE TABLE team_results (
  id     INT PRIMARY KEY,
  team   VARCHAR(20) NOT NULL,
  season INT         NOT NULL,
  wins   INT         NOT NULL,
  games  INT         NOT NULL
);
INSERT INTO team_results (id, team, season, wins, games) VALUES
  (1, 'Hawks', 2021, 7, 12), (2, 'Hawks', 2022, 8, 12),
  (3, 'Hawks', 2023, 10, 14), (4, 'Lions', 2021, 5, 10),
  (5, 'Lions', 2022, 6, 10), (6, 'Owls', 2022, 0, 8);
