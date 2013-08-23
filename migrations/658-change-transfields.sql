-- * categories.name *

-- TODO: Before proceeding, migrate all categories names in
-- Translations table to L10n data store.

alter table categories drop foreign key name_refs_id_e052037f;
alter table categories drop column name;
alter table categories add column name text;
