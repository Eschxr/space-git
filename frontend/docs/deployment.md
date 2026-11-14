# Deployment and phone capture

## Public read-only demo

Current verified demo: [spacegit-3d.vercel.app](https://spacegit-3d.vercel.app).

Deploy the repository root to the authenticated SpaceGit project with Node 24. The root `vercel.json` runs the frozen pnpm install and builds a static export with local edge access disabled. It publishes `apps/web/out`. For an authenticated Vercel CLI, verify the linked account and project, run `vercel` for a preview, then `vercel --prod` to publish the reviewed demo. Run `node scripts/check-public.mjs https://spacegit-3d.vercel.app` to verify all public routes, the bundled replay, and the absence of off-origin requests or WebSockets.

The local operational studio is protected by its operator key. The public site has no hardware relay. Avoid configuring hardware or upload secrets in the public project. Hosted authentication/relay for operator access is out of scope.

## Optional HTTPS phone gateway

On a private reachable network, build a static export for your capture host:

```powershell
$env:SPACEGIT_STATIC = '1'
$env:NEXT_PUBLIC_SPACEGIT_PUBLIC = '1'
pnpm build
```

Serve `apps/web/out` at a trusted HTTPS origin using the [Caddy example](../scripts/Caddyfile.example). Replace the domain and static root and configure trusted TLS (on a private LAN, install the local CA on the phone only if you control both devices). Set `SPACEGIT_MOBILE_ORIGIN` to the exact origin before starting the edge. Forward only the three method-scoped capture routes in the example: upload, paired status and a reconstruction request. The gateway caps upload sizes and forwards the exact HTTPS origin to the edge. Requests to `/api/v1/status`, `/api/v1/reconstructions` or `/ws/live` on the gateway should return 404. The public Vercel demo has no gateway.

From the local studio, select a revision in **Phone capture** and create a phone link. Open it in Safari or Chrome. Take several photos or choose files, then tap **Upload**. If the connection drops, retry only failed photos. Duplicate bytes on a revision are deduplicated, and completed uploads are associated with this capture session. JPEG/PNG orientation is normalized for reconstruction. Other formats are converted only if the browser can decode them; otherwise export JPEG. With at least six photos, the phone can request a result type. The local operator selects the session and queues the actual worker job. The capture view needs network access to the configured gateway.
