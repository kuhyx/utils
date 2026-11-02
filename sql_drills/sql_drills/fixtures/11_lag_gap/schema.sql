CREATE TABLE logins (
  user_name VARCHAR(10) NOT NULL,
  login_on  DATE        NOT NULL,
  PRIMARY KEY (user_name, login_on)
);
INSERT INTO logins (user_name, login_on) VALUES
  ('amy', '2023-01-01'), ('amy', '2023-01-02'), ('amy', '2023-01-10'),
  ('amy', '2023-01-17'), ('amy', '2023-02-01'), ('bo', '2023-03-01'),
  ('bo', '2023-03-05'), ('cat', '2023-01-05'), ('dan', '2024-02-20'),
  ('dan', '2024-03-01');
