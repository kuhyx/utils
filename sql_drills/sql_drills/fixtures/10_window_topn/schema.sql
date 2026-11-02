CREATE TABLE employees (
  id     INT PRIMARY KEY,
  name   VARCHAR(10) NOT NULL,
  dept   VARCHAR(10) NOT NULL,
  salary INT         NOT NULL
);
INSERT INTO employees (id, name, dept, salary) VALUES
  (1, 'Ava', 'Eng', 150), (2, 'Ben', 'Eng', 150), (3, 'Cal', 'Eng', 130),
  (4, 'Dev', 'Eng', 120), (5, 'Eli', 'Eng', 120), (6, 'Fay', 'Ops', 90),
  (7, 'Gus', 'Ops', 80), (8, 'Hal', 'Ops', 70), (9, 'Ivy', 'Sales', 100),
  (10, 'Jon', 'Sales', 100), (11, 'Kim', 'Sales', 100);
