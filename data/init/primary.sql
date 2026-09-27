-- Helios primary-db init
-- =========================================================================
-- Schema inspirado en el B2B SaaS de accounts payable que Helios ofrece.
-- En prod sería resultado de migrations; acá es solo bootstrap para el POC.
-- =========================================================================

CREATE SCHEMA IF NOT EXISTS helios;

CREATE TABLE IF NOT EXISTS helios.customers (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    tier        TEXT NOT NULL CHECK (tier IN ('starter', 'growth', 'enterprise')),
    mrr_cents   BIGINT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS helios.invoices (
    id          TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES helios.customers(id),
    amount_cents BIGINT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'flagged', 'cancelled')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invoices_customer ON helios.invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON helios.invoices(status);

-- Tabla legacy: simula los usuarios que existen ANTES de la migración a un
-- nuevo sistema de identidad. identity-bridge resuelve contra esta tabla.
CREATE TABLE IF NOT EXISTS helios.legacy_users (
    user_public_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email          TEXT NOT NULL UNIQUE,
    -- Hash sample para POC. NO usar el algoritmo de prod.
    password_hash  TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tabla de links: lo que un sistema externo (Auth0, Authentik, lo que sea)
-- usa para mapear identidades nuevas a las viejas durante la migración.
CREATE TABLE IF NOT EXISTS helios.identity_link (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    oidc_id        TEXT NOT NULL,
    user_public_id UUID NOT NULL REFERENCES helios.legacy_users(user_public_id),
    UNIQUE (oidc_id, user_public_id)
);

-- Seed mínimo para que el ETL del warehouse-job tenga algo que procesar.
INSERT INTO helios.customers (id, name, tier, mrr_cents) VALUES
    ('cus_001', 'Acme Capital',     'enterprise', 1200000),
    ('cus_002', 'Banc Genial',      'growth',      450000),
    ('cus_003', 'Northstar Pay',    'enterprise', 1800000),
    ('cus_004', 'Stellar Lending',  'starter',     120000)
ON CONFLICT (id) DO NOTHING;

INSERT INTO helios.invoices (id, customer_id, amount_cents, status) VALUES
    ('inv_001', 'cus_001', 12500,  'paid'),
    ('inv_002', 'cus_001', 49900,  'pending'),
    ('inv_003', 'cus_002', 2400,   'paid'),
    ('inv_004', 'cus_003', 120000, 'paid'),
    ('inv_005', 'cus_003', 8400,   'flagged'),
    ('inv_006', 'cus_004', 600,    'pending')
ON CONFLICT (id) DO NOTHING;

INSERT INTO helios.legacy_users (user_public_id, email, password_hash) VALUES
    ('11111111-1111-1111-1111-111111111111',
     'demo.user@helios.example',
     '$2b$04$KIXQ6a2m0z8yQ0m0m0m0m.u9J6yQe1s2Qm0z8yQ0m0m0m0m0m0m0e')
ON CONFLICT DO NOTHING;
