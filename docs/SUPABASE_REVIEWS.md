# Recensioni centrali su Supabase (MultiHotel)

Le ~600+ recensioni Apice vivono su **Apice MultiHotel**, non nel SQLite locale di Eye Supremo.

## Dove sono

| Campo | Valore |
|-------|--------|
| Progetto | **Apice MultiHotel** · `ooqlfldcrnkudhgjnied` |
| Tabella | `public.eye_central_reviews` |
| RPC lettura | `eye_central_review_page(p_username, p_pin, p_limit, p_offset, p_since)` |
| RPC scrittura | `eye_central_review_upsert(p_username, p_pin, payload jsonb)` |

Colonne usate dall’UI:

`sync_uuid`, `hotel_code`, `author`, `source`, `rating`, `review_date`, `text`, `room_code`, `updated_at`

Codici hotel in tabella → sezioni UI:

| `hotel_code` | UI |
|--------------|-----|
| `gio` | Hotel Giò |
| `choco` | Chocohotel |
| `brigantino` | Il Brigantino |

Fonti tipiche: Booking, TripAdvisor, Google, TXT (digest MSG).

## Config Eye Supremo

Nel `.env` del PC (stesso MultiHotel delle fatture):

```env
RANDFATTURE_SUPABASE_URL=https://ooqlfldcrnkudhgjnied.supabase.co
RANDFATTURE_SUPABASE_ANON_KEY=...   # publishable/anon (o SERVICE_KEY)
RANDFATTURE_SUPABASE_CENTRAL_USERNAME=sviluppatore
RANDFATTURE_SUPABASE_CENTRAL_PIN=... # PIN MultiHotel
```

Poi in app: area **Recensioni** → `GET /api/storage/central/reviews`.

Senza PIN/chiave la pagina resta vuota con messaggio di configurazione.

## Nota gateway

L’Edge `eye-central-gateway` oggi espone soprattutto `invoice_page`.
Le recensioni passano dalla **RPC** `eye_central_review_page` (con fallback gateway `review_page` se abilitato lato MultiHotel).
