-- Migration 000004 Down: Drop users index and table
DROP INDEX IF EXISTS idx_users_username;
DROP TABLE IF EXISTS users;
