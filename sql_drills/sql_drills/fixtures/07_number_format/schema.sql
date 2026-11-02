CREATE TABLE invoices (
  id       INT PRIMARY KEY,
  customer VARCHAR(20)    NOT NULL,
  amount   DECIMAL(12, 2) NOT NULL
);
INSERT INTO invoices (id, customer, amount) VALUES
  (1, 'Acme', 1200.50), (2, 'Acme', 33999.99), (3, 'Acme', 0.10),
  (4, 'Bolt', 999.99), (5, 'Cog', 1000000.00), (6, 'Cog', 2500.25),
  (7, 'Dyn', 5.00), (8, 'Dyn', 4.00);
