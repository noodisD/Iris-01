-- 0036_places_and_days.sql
--
-- Named places and a day-level cache. The cache is built only from confirmed
-- observations and holds no coordinates. The phone never receives the places.

CREATE TABLE places (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    kind        TEXT NOT NULL CHECK (kind IN ('home', 'office', 'other')),
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    radius_m    INTEGER NOT NULL DEFAULT 150 CHECK (radius_m > 0),
    source      TEXT NOT NULL CHECK (source IN ('owner', 'timeline')),
    UNIQUE (user_id, name)
);

CREATE INDEX places_user_kind ON places (user_id, kind);

CREATE TABLE app_categories (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    package     TEXT NOT NULL CHECK (length(btrim(package)) > 0),
    category    TEXT NOT NULL CHECK (length(btrim(category)) > 0),
    PRIMARY KEY (user_id, package)
);

CREATE TABLE day_features (
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day                 DATE NOT NULL,
    day_kind            TEXT NOT NULL CHECK (day_kind IN ('office', 'home', 'other', 'unknown')),
    home_minutes        INTEGER NOT NULL DEFAULT 0,
    office_minutes      INTEGER NOT NULL DEFAULT 0,
    commute_minutes     INTEGER NOT NULL DEFAULT 0,
    commute_mode        TEXT,
    steps               INTEGER,
    steps_full_day      BOOLEAN NOT NULL DEFAULT FALSE,
    screen_minutes      INTEGER NOT NULL DEFAULT 0,
    screen_by_category  JSONB NOT NULL DEFAULT '{}'::jsonb,
    sleep_minutes       INTEGER,
    location_coverage   DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
