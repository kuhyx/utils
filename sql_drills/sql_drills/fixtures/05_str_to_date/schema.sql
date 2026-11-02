CREATE TABLE signups (
  id          INT PRIMARY KEY,
  email       VARCHAR(40) NOT NULL,
  signup_text VARCHAR(20) NOT NULL
);
INSERT INTO signups (id, email, signup_text) VALUES
  (1, 'a@example.org', '03/14/2022 18:45'),
  (2, 'b@example.org', '12/01/2021 08:00'),
  (3, 'c@example.org', '03/02/2022 23:10'),
  (4, 'd@example.org', '11/30/2022 00:00'),
  (5, 'e@example.org', '01/09/2022 12:30'),
  (6, 'f@example.org', '03/01/2022 00:00'),
  (7, 'g@example.org', '02/28/2023 07:05');
