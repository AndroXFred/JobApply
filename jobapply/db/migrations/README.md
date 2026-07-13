Future hand-written schema migrations go here as numbered `.sql` files
(e.g. `0002_add_x.sql`), applied by a new entry in `jobapply/db/migrate.py`'s
`MIGRATIONS` list. `0001_init` builds the initial schema directly from
`jobapply/db/models.py` rather than a duplicated `.sql` file, so it can
never drift from the ORM models.
