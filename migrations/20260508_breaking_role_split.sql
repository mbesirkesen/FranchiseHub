-- Breaking migration: split users table into role-specific tables.
-- Target: PostgreSQL (Neon compatible)

BEGIN;

-- 1) Drop old foreign key constraints and legacy tables.
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS applications CASCADE;
DROP TABLE IF EXISTS inventories CASCADE;
DROP TABLE IF EXISTS supply_requests CASCADE;
DROP TABLE IF EXISTS brands CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- 2) Drop legacy enum types if they exist.
DROP TYPE IF EXISTS user_role CASCADE;
DROP TYPE IF EXISTS application_status CASCADE;
DROP TYPE IF EXISTS supply_request_status CASCADE;
DROP TYPE IF EXISTS message_sender_role CASCADE;

-- 3) Recreate enum types.
CREATE TYPE user_role AS ENUM ('buyer', 'franchise_owner', 'admin');
CREATE TYPE application_status AS ENUM ('pending', 'approved', 'rejected');
CREATE TYPE supply_request_status AS ENUM ('pending', 'approved', 'rejected');
CREATE TYPE message_sender_role AS ENUM ('buyer', 'franchise_owner', 'admin');

-- 4) Role-specific identity tables.
CREATE TABLE buyers (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    city VARCHAR(120) NOT NULL,
    investment_budget DOUBLE PRECISION NOT NULL,
    experience_years INTEGER NOT NULL DEFAULT 0,
    preferred_sector VARCHAR(120) NOT NULL,
    identity_number VARCHAR(50) UNIQUE
);

CREATE TABLE franchise_owners (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    company_name VARCHAR(255) NOT NULL,
    tax_number VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(30) NOT NULL,
    authorized_person_name VARCHAR(180) NOT NULL,
    country VARCHAR(120) NOT NULL,
    city VARCHAR(120) NOT NULL,
    company_address TEXT NOT NULL,
    website VARCHAR(255),
    verification_status BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE admins (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    full_name VARCHAR(180) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    authorization_level VARCHAR(50) NOT NULL DEFAULT 'standard',
    is_superadmin BOOLEAN NOT NULL DEFAULT FALSE
);

-- 5) Business domain tables.
CREATE TABLE brands (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    franchise_owner_id INTEGER REFERENCES franchise_owners(id),
    sector VARCHAR(255),
    description TEXT,
    initial_cost DOUBLE PRECISION NOT NULL,
    support_details TEXT,
    location VARCHAR(255),
    is_approved BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE applications (
    id SERIAL PRIMARY KEY,
    buyer_id INTEGER NOT NULL REFERENCES buyers(id),
    brand_id INTEGER NOT NULL REFERENCES brands(id),
    status application_status NOT NULL DEFAULT 'pending',
    notes TEXT
);

CREATE TABLE inventories (
    id SERIAL PRIMARY KEY,
    franchise_owner_id INTEGER NOT NULL REFERENCES franchise_owners(id),
    item_name VARCHAR(255) NOT NULL,
    stock_level INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE supply_requests (
    id SERIAL PRIMARY KEY,
    franchise_owner_id INTEGER NOT NULL REFERENCES franchise_owners(id),
    product_name VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL,
    status supply_request_status NOT NULL DEFAULT 'pending'
);

CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id),
    sender_role message_sender_role NOT NULL,
    sender_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- 6) Essential indexes.
CREATE INDEX ix_buyers_email ON buyers(email);
CREATE INDEX ix_franchise_owners_email ON franchise_owners(email);
CREATE INDEX ix_admins_email ON admins(email);
CREATE INDEX ix_brands_name ON brands(name);
CREATE INDEX ix_brands_franchise_owner_id ON brands(franchise_owner_id);
CREATE INDEX ix_applications_buyer_id ON applications(buyer_id);
CREATE INDEX ix_applications_brand_id ON applications(brand_id);
CREATE INDEX ix_supply_requests_franchise_owner_id ON supply_requests(franchise_owner_id);
CREATE INDEX ix_inventories_franchise_owner_id ON inventories(franchise_owner_id);
CREATE INDEX ix_messages_application_id ON messages(application_id);
CREATE INDEX ix_messages_sender_id ON messages(sender_id);

COMMIT;
