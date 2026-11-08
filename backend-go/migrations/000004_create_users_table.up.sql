-- Migration 000004: Create users table and index for authentication and RBAC (ADR-0005)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('ADMIN', 'OPERATOR', 'VIEWER')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_username ON users(username);

-- Seed default test accounts (admin, operator01, viewer01)
INSERT INTO users (username, password_hash, role, is_active)
VALUES
    ('admin', '$2a$12$rmJ2Pz.QrfLOPN5b84ynfOH7W1t9zj0YZA4ktNQfGAecMvt1BssUO', 'ADMIN', true),
    ('operator01', '$2a$12$O.kdBztNJ9KxS8laSwimDembCHdv8YnTtC46R2RgrxgFOS/SygGVW', 'OPERATOR', true),
    ('viewer01', '$2a$12$Nn.8oETwy1a1UMG07GFtc.eSfRap0O8b8IV6th2AM23Y72j0/Ikli', 'VIEWER', true)
ON CONFLICT (username) DO NOTHING;

