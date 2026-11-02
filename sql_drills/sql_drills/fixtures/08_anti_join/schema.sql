CREATE TABLE customers (
  id    INT PRIMARY KEY,
  name  VARCHAR(20) NOT NULL,
  phone VARCHAR(20) NULL
);
CREATE TABLE orders (
  id          INT PRIMARY KEY,
  customer_id INT         NOT NULL,
  status      VARCHAR(10) NOT NULL
);
INSERT INTO customers (id, name, phone) VALUES
  (1, 'Alma', '555-0101'), (2, 'Boris', NULL), (3, 'Cleo', '555-0103'),
  (4, 'Dara', NULL), (5, 'Egon', '555-0105');
INSERT INTO orders (id, customer_id, status) VALUES
  (1, 1, 'shipped'), (2, 3, 'cancelled'), (3, 3, 'cancelled'),
  (4, 5, 'pending'), (5, 1, 'cancelled');
