-- Private backend schema. Never add auction_private to PostgREST exposed schemas.
-- Apply through the database operator connection, never the browser/public key.
CREATE SCHEMA IF NOT EXISTS auction_private;
REVOKE ALL ON SCHEMA auction_private FROM PUBLIC, anon, authenticated;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='auction_api') THEN
        CREATE ROLE auction_api NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END $$;
GRANT USAGE ON SCHEMA auction_private TO auction_api;
SET LOCAL search_path TO auction_private, pg_catalog;
CREATE TABLE IF NOT EXISTS schema_version(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(user_id TEXT PRIMARY KEY,customer_id TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS saved(user_id TEXT NOT NULL,property_id TEXT NOT NULL,created_at BIGINT NOT NULL,PRIMARY KEY(user_id,property_id));
CREATE TABLE IF NOT EXISTS subscriptions(subscription_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,plan TEXT NOT NULL,status TEXT NOT NULL,valid_until BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS webhook_events(event_id TEXT PRIMARY KEY,processed_at BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS purchases(order_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,product TEXT NOT NULL,property_id TEXT NOT NULL,price_id TEXT NOT NULL,session_id TEXT UNIQUE,payment_intent TEXT,status TEXT NOT NULL,created_at BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS workspace(user_id TEXT NOT NULL,property_id TEXT NOT NULL,watched INTEGER NOT NULL DEFAULT 0,notes TEXT NOT NULL DEFAULT '',target_price DOUBLE PRECISION,observation TEXT,updated_at BIGINT NOT NULL,PRIMARY KEY(user_id,property_id));
CREATE TABLE IF NOT EXISTS saved_searches(user_id TEXT NOT NULL,search_id TEXT NOT NULL,name TEXT NOT NULL,query TEXT NOT NULL,digest INTEGER NOT NULL DEFAULT 0,created_at BIGINT NOT NULL,PRIMARY KEY(user_id,search_id));
CREATE TABLE IF NOT EXISTS watch_events(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,property_id TEXT NOT NULL,event_json TEXT NOT NULL,created_at BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,property_id TEXT NOT NULL,report_json TEXT NOT NULL,created_at BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS review_processing(review_id TEXT PRIMARY KEY,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,updated_at BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS deals(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,body TEXT NOT NULL,version INTEGER NOT NULL,updated_at BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS deal_enquiries(id TEXT PRIMARY KEY,deal_id TEXT NOT NULL,name TEXT NOT NULL,email TEXT NOT NULL,message TEXT NOT NULL,created_at BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS deal_metrics(deal_id TEXT NOT NULL,metric TEXT NOT NULL,count BIGINT NOT NULL DEFAULT 0,PRIMARY KEY(deal_id,metric));
CREATE INDEX IF NOT EXISTS subscriptions_account ON subscriptions(user_id,valid_until);
CREATE INDEX IF NOT EXISTS purchases_account_order ON purchases(user_id,product,property_id,created_at);
CREATE INDEX IF NOT EXISTS purchases_payment ON purchases(payment_intent);
CREATE INDEX IF NOT EXISTS watch_events_account_time ON watch_events(user_id,created_at);
CREATE INDEX IF NOT EXISTS reviews_account_time ON reviews(user_id,created_at);
CREATE INDEX IF NOT EXISTS deals_owner ON deals(owner_id);
CREATE INDEX IF NOT EXISTS enquiries_deal ON deal_enquiries(deal_id);
CREATE INDEX IF NOT EXISTS enquiries_email_time ON deal_enquiries(email,created_at);
REVOKE ALL ON ALL TABLES IN SCHEMA auction_private FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA auction_private TO auction_api;
-- Only this backend role can access these private tables. Per-customer ownership
-- is enforced by the verified-identity API, not editable JWT user_metadata.
DO $$ DECLARE item record; BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='auction_private' LOOP
        EXECUTE format('ALTER TABLE auction_private.%I ENABLE ROW LEVEL SECURITY',item.tablename);
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='auction_private'
                       AND tablename=item.tablename AND policyname='backend_only') THEN
            EXECUTE format('CREATE POLICY backend_only ON auction_private.%I TO auction_api USING (true) WITH CHECK (true)',item.tablename);
        END IF;
    END LOOP;
END $$;
INSERT INTO schema_version(id,version) VALUES (1,1) ON CONFLICT(id) DO NOTHING;
REVOKE INSERT,UPDATE,DELETE ON schema_version FROM auction_api;
