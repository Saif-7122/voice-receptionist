-- ============================================================
-- AI Voice Receptionist — Supabase Schema
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
-- ============================================================

-- Enable pgvector extension for similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- ── businesses ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS businesses (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  name                 TEXT NOT NULL,
  category             TEXT,                        -- gym | cafe | clinic | restaurant
  description          TEXT,
  hours                JSONB,                       -- { "mon": "9am–9pm", … }
  location             TEXT,
  phone                TEXT,
  vapi_assistant_id    TEXT,                        -- set after Vapi assistant is created
  n8n_webhook_url      TEXT,
  elevenlabs_voice_id  TEXT,
  created_at           TIMESTAMPTZ DEFAULT now(),
  updated_at           TIMESTAMPTZ DEFAULT now()
);

-- ── faqs ──────────────────────────────────────────────────────────────────
-- Raw FAQ text (before chunking). Source of truth for the dashboard editor.
CREATE TABLE IF NOT EXISTS faqs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id  UUID REFERENCES businesses(id) ON DELETE CASCADE,
  question     TEXT NOT NULL,
  answer       TEXT NOT NULL,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- ── knowledge_chunks (LangChain SupabaseVectorStore convention) ───────────
-- Column names MUST be: content, metadata, embedding
-- LangChain's SupabaseVectorStore.from_documents() writes to these columns.
CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id           BIGSERIAL PRIMARY KEY,
  business_id  UUID REFERENCES businesses(id) ON DELETE CASCADE,
  content      TEXT NOT NULL,          -- chunk text  → LangChain page_content
  metadata     JSONB,                  -- chunk meta  → LangChain Document.metadata
  embedding    vector(384),            -- BAAI/bge-small-en-v1.5 output dim = 384
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- IVFFlat index for approximate nearest-neighbour cosine search
-- lists = 100 is a good default for < 1M rows; increase for larger datasets
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
  ON knowledge_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Secondary index for fast per-business filtering
CREATE INDEX IF NOT EXISTS knowledge_chunks_business_idx
  ON knowledge_chunks (business_id);

-- ── match_documents (required by LangChain SupabaseVectorStore) ───────────
-- LangChain calls this Postgres function for similarity_search().
-- It must exist before you call SupabaseVectorStore.similarity_search().
CREATE OR REPLACE FUNCTION match_documents (
  query_embedding  vector(384),
  match_count      INT DEFAULT 4,
  filter           JSONB DEFAULT '{}'
)
RETURNS TABLE (
  id        BIGINT,
  content   TEXT,
  metadata  JSONB,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    knowledge_chunks.id,
    knowledge_chunks.content,
    knowledge_chunks.metadata,
    1 - (knowledge_chunks.embedding <=> query_embedding) AS similarity
  FROM knowledge_chunks
  WHERE
    CASE
      WHEN filter ? 'business_id'
        THEN knowledge_chunks.metadata->>'business_id' = filter->>'business_id'
      ELSE TRUE
    END
  ORDER BY knowledge_chunks.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ── patients ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS patients (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id     UUID REFERENCES businesses(id) ON DELETE CASCADE,
  name            TEXT,
  phone_number    TEXT,
  age             INT,
  membership_status TEXT,      -- 'active' | 'expired' | 'none'
  membership_expiry DATE,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── treatment_history ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS treatment_history (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id   UUID REFERENCES patients(id) ON DELETE CASCADE,
  visit_date   DATE,
  treatment    TEXT,
  doctor_name  TEXT,
  notes        TEXT
);

-- ── appointments ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS appointments (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id        UUID REFERENCES businesses(id) ON DELETE CASCADE,
  patient_id         UUID REFERENCES patients(id) ON DELETE SET NULL,
  call_id            TEXT,
  patient_name       TEXT NOT NULL,
  patient_whatsapp   TEXT NOT NULL,
  confirmed_date     TEXT NOT NULL,
  confirmed_time     TEXT NOT NULL,
  confirmed_reason   TEXT,
  confirmation_code  TEXT UNIQUE DEFAULT upper(substr(md5(random()::text), 1, 8)),
  status             TEXT DEFAULT 'booked',    -- booked | cancelled | completed
  created_at         TIMESTAMPTZ DEFAULT now()
);


-- ── call_logs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS call_logs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id   UUID REFERENCES businesses(id) ON DELETE CASCADE,
  vapi_call_id  TEXT,
  transcript    TEXT,
  summary       TEXT,
  escalated     BOOLEAN DEFAULT false,
  duration_sec  INTEGER,
  caller_info   JSONB,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- ── Row-Level Security ────────────────────────────────────────────────────
-- Owners can only see and modify their own business data.

ALTER TABLE businesses       ENABLE ROW LEVEL SECURITY;
ALTER TABLE faqs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments     ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients         ENABLE ROW LEVEL SECURITY;
ALTER TABLE treatment_history ENABLE ROW LEVEL SECURITY;

-- businesses
CREATE POLICY "owner_access" ON businesses
  USING (owner_id = auth.uid());

-- faqs
CREATE POLICY "owner_access" ON faqs
  USING (business_id IN (
    SELECT id FROM businesses WHERE owner_id = auth.uid()
  ));

-- knowledge_chunks
CREATE POLICY "owner_access" ON knowledge_chunks
  USING (business_id IN (
    SELECT id FROM businesses WHERE owner_id = auth.uid()
  ));

-- appointments
CREATE POLICY "owner_access" ON appointments
  USING (business_id IN (
    SELECT id FROM businesses WHERE owner_id = auth.uid()
  ));

-- call_logs
CREATE POLICY "owner_access" ON call_logs
  USING (business_id IN (
    SELECT id FROM businesses WHERE owner_id = auth.uid()
  ));

-- patients
CREATE POLICY "owner_access" ON patients
  USING (business_id IN (
    SELECT id FROM businesses WHERE owner_id = auth.uid()
  ));

-- treatment_history
CREATE POLICY "owner_access" ON treatment_history
  USING (patient_id IN (
    SELECT id FROM patients WHERE business_id IN (
      SELECT id FROM businesses WHERE owner_id = auth.uid()
    )
  ));

-- ── updated_at trigger for businesses ─────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER businesses_updated_at
  BEFORE UPDATE ON businesses
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
