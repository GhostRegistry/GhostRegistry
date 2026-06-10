GhostRegistry v11 - Stabilize + Playable Casino Push

What changed:
- Rebuilt the casino game template so Blackjack, Poker, Roulette, Baccarat, Slots, Video Poker, and Jackpot Vault are self-contained playable pages.
- Added direct casino game links to the Dashboard under Economy + Arcade.
- Added visible How To Play buttons inside each casino game.
- Added safer local Ghost Shards display updates if Supabase settlement fails, so the page still plays instead of feeling broken.
- Kept the /casino/settle route for real Ghost Shards updates when Supabase tables/columns are correct.
- Added live session checker to Dashboard for faster kick-outs.
- Added extra avatar fallback styling to reduce black profile picture issues.

Testing path:
1. Run supabase_upgrade.sql in Supabase.
2. Upload this folder/ZIP to Render.
3. Open Dashboard > Economy + Arcade.
4. Test the direct game links: Playable Blackjack, Playable Poker, Playable Roulette, Playable Slots, Video Poker, Jackpot Vault.
5. If old pages seem cached, press Ctrl + F5 in the browser.

Important:
This is still a Flask web app, not a true mobile app/WebSocket/multiplayer platform yet. The remaining giant roadmap systems are represented as pages and hubs, while this update focuses on making the current website more stable and actually playable.
