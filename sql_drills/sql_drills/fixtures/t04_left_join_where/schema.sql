CREATE TABLE customers (id INT, name VARCHAR(10), referee INT);
INSERT INTO customers VALUES (1, 'Ann', NULL), (2, 'Bob', 1), (3, 'Cid', 2), (4, 'Dee', NULL);
CREATE TABLE orders (id INT, customer_id INT, amount INT, status VARCHAR(10));
INSERT INTO orders VALUES (10, 1, 50, 'paid'), (11, 1, 70, 'refunded'), (12, 2, 30, 'paid');
