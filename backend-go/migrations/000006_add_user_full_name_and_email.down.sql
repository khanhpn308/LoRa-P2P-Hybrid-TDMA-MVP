-- Migration 000005 Down: Drop full_name and email columns
ALTER TABLE users DROP COLUMN IF EXISTS email;
ALTER TABLE users DROP COLUMN IF EXISTS full_name;
