-- Execute explicitly as a database administrator on the local MySQL instance.
-- This script only creates the application database; it does not create users.
CREATE DATABASE IF NOT EXISTS smart_travel
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Provision separate local application and migration accounts outside this file.
-- Replace account placeholders before manually executing a GRANT statement.
-- Runtime account needs SELECT, INSERT, UPDATE, DELETE on smart_travel.*.
-- Migration account additionally needs CREATE, ALTER, DROP, INDEX, REFERENCES.
-- Example (commented out):
-- GRANT SELECT, INSERT, UPDATE, DELETE ON smart_travel.*
--     TO '<application-user>'@'127.0.0.1';
-- Keep passwords in backend/.env and use URL encoding in DATABASE_URL.
