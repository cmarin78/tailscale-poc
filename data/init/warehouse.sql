-- Helios warehouse-db init
-- =========================================================================
-- El warehouse es ESCRITO solo por warehouse-job. data-eng lo lee para BI.
-- El schema es dimensional-light: una fact table de invoices (denormalizada)
-- y aggregates precomputadas por el job.
-- =========================================================================

CREATE SCHEMA IF NOT EXISTS helios_dw;

-- Fact table: una fila por invoice, denormalizada con customer info.
CREATE TABLE IF NOT EXISTS helios_dw.fact_invoices (
    invoice_id     TEXT PRIMARY KEY,
    customer_id    TEXT NOT NULL,
    customer_tier  TEXT NOT NULL,
    customer_name  TEXT NOT NULL,
    amount_cents   BIGINT NOT NULL,
    status         TEXT NOT NULL,
    invoice_date   DATE NOT NULL,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_invoices_customer ON helios_dw.fact_invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_fact_invoices_date ON helios_dw.fact_invoices(invoice_date);

-- Aggregate table: la que warehouse-job mantiene actualizada.
CREATE TABLE IF NOT EXISTS helios_dw.invoice_aggregates (
    customer_id    TEXT PRIMARY KEY,
    total_cents    BIGINT NOT NULL,
    paid_cents     BIGINT NOT NULL,
    invoice_count  INT NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Vista para data-eng: invoice mix por tier y mes.
CREATE OR REPLACE VIEW helios_dw.v_invoice_mix_by_tier AS
SELECT
    customer_tier,
    DATE_TRUNC('month', invoice_date) AS month,
    COUNT(*) AS invoice_count,
    SUM(amount_cents) AS total_cents,
    AVG(amount_cents) AS avg_cents
FROM helios_dw.fact_invoices
GROUP BY customer_tier, DATE_TRUNC('month', invoice_date);
