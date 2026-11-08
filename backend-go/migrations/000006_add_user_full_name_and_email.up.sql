-- Migration 000005: Add full_name and email to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(128) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(128) NOT NULL DEFAULT '';

-- Backfill default seed users if empty
UPDATE users SET full_name = 'Quản trị viên Hệ thống', email = 'admin@iiot-lora.vn' WHERE username = 'admin' AND full_name = '';
UPDATE users SET full_name = 'Trần Vận Hành', email = 'operator01@iiot-lora.vn' WHERE username = 'operator01' AND full_name = '';
UPDATE users SET full_name = 'Người Xem Kiểm Toán', email = 'viewer01@iiot-lora.vn' WHERE username = 'viewer01' AND full_name = '';
