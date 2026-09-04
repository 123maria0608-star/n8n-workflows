-- Tables used by workflows 06, 07 and 08. Run once per database:
--   psql -h localhost -p 5433 -U n8n -d n8ndemo -f demo/schema.sql

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per n8n workflow, with a vector of its description for nearest-neighbour search.
CREATE TABLE IF NOT EXISTS workflow_index (
  id           text PRIMARY KEY,          -- the n8n workflow id
  name         text NOT NULL,
  description  text NOT NULL,             -- what the indexer built the vector from
  trigger      text NOT NULL,             -- e.g. "webhook POST /lead", "schedule 0 10 * * 1-5"
  node_count   integer NOT NULL,
  active       boolean NOT NULL,
  embedding    vector(256) NOT NULL,      -- unit-length; cosine distance is 1 - dot product
  indexed_at   timestamptz NOT NULL DEFAULT now()
);

-- Every question the chatbot was asked, what it answered, and how sure it was.
CREATE TABLE IF NOT EXISTS chat_log (
  id                   bigserial PRIMARY KEY,
  session_id           text NOT NULL,
  question             text NOT NULL,
  answer               text NOT NULL,
  matched_workflow_id  text REFERENCES workflow_index(id),
  similarity           real,              -- cosine similarity of question vs. matched description, 0..1
  asked_at             timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_log_session_idx ON chat_log (session_id, asked_at);

-- PDF text for deterministic (full-text) search: one row per chunk of a document.
-- tsv is maintained by Postgres itself from content; the GIN index makes @@ fast.
CREATE TABLE IF NOT EXISTS docs (
  id          bigserial PRIMARY KEY,
  name        text NOT NULL,                -- file name inside the PDF folder
  chunk_no    integer NOT NULL,
  n_chunks    integer NOT NULL,
  content     text NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  indexed_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (name, chunk_no)
);
CREATE INDEX IF NOT EXISTS docs_tsv_idx ON docs USING GIN (tsv);
