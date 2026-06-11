-- Kullaniciya gorunen alanlardan [DEMO] isaretlerini kaldir.
-- Calistirma: psql "$DATABASE_URL" -f migrations/20260526_strip_demo_markers.sql

UPDATE brands
SET support_details = TRIM(BOTH FROM REPLACE(support_details, '[DEMO] ', ''))
WHERE support_details LIKE '%[DEMO]%';

UPDATE brands
SET description = TRIM(BOTH FROM REPLACE(description, '[DEMO] ', ''))
WHERE description LIKE '%[DEMO]%';

UPDATE franchise_owners
SET company_address = TRIM(BOTH FROM REPLACE(company_address, ' — [DEMO]', ''))
WHERE company_address LIKE '%[DEMO]%';

UPDATE brand_territories
SET name = TRIM(BOTH FROM REPLACE(name, '[DEMO] ', ''))
WHERE name LIKE '%[DEMO]%';

UPDATE franchise_outlets
SET name = TRIM(BOTH FROM REPLACE(name, '[DEMO] ', ''))
WHERE name LIKE '%[DEMO]%';

UPDATE brand_fdd_documents
SET title = TRIM(BOTH FROM REPLACE(title, '[DEMO] ', ''))
WHERE title LIKE '%[DEMO]%';

UPDATE inventories
SET item_name = TRIM(BOTH FROM REPLACE(item_name, '[DEMO] ', ''))
WHERE item_name LIKE '%[DEMO]%';

UPDATE supply_requests
SET product_name = TRIM(BOTH FROM REPLACE(product_name, '[DEMO] ', ''))
WHERE product_name LIKE '%[DEMO]%';

UPDATE franchise_owner_documents
SET title = TRIM(BOTH FROM REPLACE(title, '[DEMO] ', ''))
WHERE title LIKE '%[DEMO]%';

UPDATE applications
SET notes = TRIM(BOTH FROM REPLACE(notes, '[DEMO] ', ''))
WHERE notes LIKE '%[DEMO]%';
