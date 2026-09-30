-- ============================================
-- Annotations Table
-- ============================================
CREATE TABLE IF NOT EXISTS annotations (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT       NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id         BIGINT       NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    type            VARCHAR(50)  NOT NULL DEFAULT 'MARKER',      -- MARKER | POLYGON
    coordinates_json TEXT        NOT NULL DEFAULT '[]',           -- JSON: [lat,lng] ou [[lat,lng],...]
    text            TEXT,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_annotations_project_id  ON annotations(project_id);
CREATE INDEX IF NOT EXISTS idx_annotations_user_id     ON annotations(user_id);
CREATE INDEX IF NOT EXISTS idx_annotations_created_at  ON annotations(created_at);
