SELECT person,
       MAX(CASE WHEN attr = 'email' THEN val END),
       MAX(CASE WHEN attr = 'phone' THEN val END),
       MAX(CASE WHEN attr = 'city' THEN val END)
FROM person_attrs
GROUP BY person
ORDER BY person;
