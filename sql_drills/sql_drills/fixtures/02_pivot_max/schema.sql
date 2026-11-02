CREATE TABLE person_attrs (
  person VARCHAR(20) NOT NULL,
  attr   VARCHAR(10) NOT NULL,
  val    VARCHAR(40) NOT NULL,
  PRIMARY KEY (person, attr)
);
INSERT INTO person_attrs (person, attr, val) VALUES
  ('Zed', 'email', 'zed@example.org'), ('Zed', 'city', 'Gdansk'),
  ('Zed', 'phone', '555-0101'), ('Ola', 'email', 'ola@example.org'),
  ('Max', 'city', 'Lodz'), ('Max', 'phone', '555-0102'),
  ('Ida', 'phone', '555-0103'), ('Ida', 'email', 'ida@example.org'),
  ('Ida', 'city', 'Krakow');
