# Eye Supremo Supabase space

Eye Supremo remains **local-first**. Supabase is temporary shared infrastructure used for synchronization/catalog metadata and private invoice blobs while the final PC backend is prepared.

## Boundary

Eye Supremo owns:

- logical database space: `eye_supremo`;
- legacy compatibility objects: `public.eye_central_*` during the staged cutover;
- private Storage bucket: `eye-invoices`;
- local PC data: SQLite/WAL under `%LOCALAPPDATA%\\EyeSupremo`.

MultiHotel owns its operational tables and Rand services. HotelGio is a separate legacy system and is explicitly out of scope.

## Transitional behavior

The shared Supabase project does **not** require a new paid project. MultiHotel migration `20261002060000_eye_supremo_space_facade.sql` creates the `eye_supremo` schema as a non-destructive facade over the existing Eye tables.

Older Eye builds continue to work because the existing `public.eye_central_*` tables/RPCs are not moved or renamed.

The environment variable:

```env
EYESUPREMO_SUPABASE_SCHEMA=eye_supremo
```

records the owned namespace. Runtime RPC compatibility remains on `public` until the gateway/client migration is completed.

## PC target

The separation is intentionally portable:

```text
Eye Supremo UI
  -> Eye backend
      -> SQLite/Postgres on PC (final)
      -> Supabase eye_supremo space (temporary sync only)
```

When the local PC backend becomes authoritative, the Supabase adapter can be removed without changing the Eye domain model.
