SELECT id, DATE_FORMAT(STR_TO_DATE(signup_text, '%m/%d/%Y %H:%i'), '%Y-%m-%d')
FROM signups
WHERE STR_TO_DATE(signup_text, '%m/%d/%Y %H:%i') >= '2022-03-01'
ORDER BY STR_TO_DATE(signup_text, '%m/%d/%Y %H:%i'), id;
