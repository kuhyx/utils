CREATE TABLE events (
  id        INT PRIMARY KEY,
  name      VARCHAR(30) NOT NULL,
  starts_at DATETIME    NOT NULL
);
INSERT INTO events (id, name, starts_at) VALUES
  (1, 'Launch party', '2021-03-05 09:07:00'),
  (2, 'Retro',        '2022-11-30 17:45:10'),
  (3, 'Offsite',      '2020-02-29 00:05:00'),
  (4, 'Standup',      '2023-07-04 12:00:00'),
  (5, 'Closing',      '2019-12-31 23:59:59');
