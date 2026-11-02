CREATE TABLE shop_sales (
  id      INT PRIMARY KEY,
  region  VARCHAR(20) NOT NULL,
  quarter CHAR(2)     NOT NULL,
  amount  INT         NOT NULL
);
INSERT INTO shop_sales (id, region, quarter, amount) VALUES
  (1, 'North', 'Q1', 120), (2, 'North', 'Q1', 80),
  (3, 'North', 'Q2', 150), (4, 'North', 'Q4', 200),
  (5, 'South', 'Q1', 90),  (6, 'South', 'Q3', 60),
  (7, 'South', 'Q3', 40),  (8, 'East', 'Q2', 300),
  (9, 'East', 'Q4', 25),   (10, 'West', 'Q1', 10);
