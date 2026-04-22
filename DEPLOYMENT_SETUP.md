# Marker Board production setup

## Supabase

1. Open your Supabase project.
2. Go to `SQL Editor`.
3. Run the full contents of `supabase_schema.sql`.
4. Go to `Project Settings` -> `API`.
5. Copy these values:
   - Project URL
   - service_role key

Do not put the service-role key in browser code. It must only be configured as a Vercel Environment Variable.

## Vercel environment variables

Add these variables to the Vercel project for Production and Preview:

```text
BOARD_PASSWORD=your-private-password
SESSION_SECRET=generate-a-long-random-string
SUPABASE_URL=https://ehvqvatfpaceaxfdnkbe.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
SUPABASE_STATE_ID=default
```

`SESSION_SECRET` can be any long random string. Example generation command:

```bash
openssl rand -hex 32
```

## Local development

For local Vercel-style testing, create `.env.local`:

```text
BOARD_PASSWORD=your-private-password
SESSION_SECRET=generate-a-long-random-string
SUPABASE_URL=https://ehvqvatfpaceaxfdnkbe.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
SUPABASE_STATE_ID=default
```

Then run with Vercel CLI:

```bash
vercel dev
```

## Security model

- The password is checked only by `/api/auth`.
- The browser stores only a signed temporary session token.
- Board data is read/written only by `/api/state`.
- Supabase service-role credentials stay server-side in Vercel environment variables.
