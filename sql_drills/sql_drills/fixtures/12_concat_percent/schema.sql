CREATE TABLE poll_votes (
  poll_id     INT         NOT NULL,
  option_name VARCHAR(10) NOT NULL,
  votes       INT         NOT NULL,
  PRIMARY KEY (poll_id, option_name)
);
INSERT INTO poll_votes (poll_id, option_name, votes) VALUES
  (1, 'Red', 3), (1, 'Green', 3), (1, 'Blue', 1),
  (2, 'Yes', 5), (2, 'No', 5),
  (3, 'Maybe', 0), (3, 'Sure', 4);
