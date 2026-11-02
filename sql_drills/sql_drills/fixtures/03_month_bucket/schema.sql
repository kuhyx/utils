CREATE TABLE orders (
  id         INT PRIMARY KEY,
  customer   VARCHAR(20)   NOT NULL,
  order_date DATETIME      NOT NULL,
  status     VARCHAR(10)   NOT NULL,
  total      DECIMAL(8, 2) NOT NULL
);
INSERT INTO orders (id, customer, order_date, status, total) VALUES
  (1, 'Ann', '2023-01-05 10:00:00', 'shipped', 100.00),
  (2, 'Bob', '2023-01-20 11:30:00', 'cancelled', 50.00),
  (3, 'Ann', '2023-01-31 23:59:59', 'shipped', 25.50),
  (4, 'Cy',  '2023-02-01 00:00:00', 'shipped', 80.00),
  (5, 'Bob', '2023-02-14 09:15:00', 'pending', 60.00),
  (6, 'Dan', '2023-02-28 18:00:00', 'cancelled', 30.00),
  (7, 'Ann', '2023-04-02 08:00:00', 'shipped', 200.00),
  (8, 'Cy',  '2023-04-30 23:00:00', 'shipped', 15.25),
  (9, 'Dan', '2023-04-30 12:00:00', 'cancelled', 99.99),
  (10, 'Bob', '2022-12-31 22:00:00', 'shipped', 10.00),
  (11, 'Eve', '2023-06-10 10:00:00', 'pending', 70.00);
