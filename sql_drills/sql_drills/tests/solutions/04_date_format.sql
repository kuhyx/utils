SELECT id,
       DATE_FORMAT(starts_at, '%W, %d %M %Y %H:%i'),
       DATE_FORMAT(starts_at, '%h:%i %p')
FROM events
ORDER BY id;
