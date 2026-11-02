CREATE TABLE tickets (
  id       INT PRIMARY KEY,
  team     VARCHAR(10)   NOT NULL,
  priority VARCHAR(10)   NOT NULL,
  hours    DECIMAL(5, 1) NOT NULL
);
INSERT INTO tickets (id, team, priority, hours) VALUES
  (1, 'Alpha', 'high', 5.0), (2, 'Alpha', 'medium', 3.5),
  (3, 'Alpha', 'low', 9.0), (4, 'Alpha', 'high', 2.5),
  (5, 'Beta', 'medium', 4.0), (6, 'Beta', 'high', 6.0),
  (7, 'Gamma', 'high', 4.0), (8, 'Gamma', 'medium', 4.0),
  (9, 'Gamma', 'high', 4.0), (10, 'Gamma', 'medium', 4.0),
  (11, 'Delta', 'medium', 1.0), (12, 'Delta', 'medium', 1.0),
  (13, 'Delta', 'low', 50.0), (14, 'Delta', 'high', 1.0),
  (15, 'Eps', 'medium', 3.5), (16, 'Eps', 'medium', 3.5),
  (17, 'Eps', 'high', 3.0);
