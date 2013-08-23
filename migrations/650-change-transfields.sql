-- addons.name
-- alter table addons drop foreign key addons_ibfk_2;

-- categories.name
-- alter table categories drop foreign key name_refs_id_e052037f;
alter table categories change column name name varchar(32);
