# Roadmap

Done 2026-09-23: phone-tested de_dust2 matches (Open Halo sandbox branch), VPK material resolution, static-prop models, non-solid prop flag.

1. **Next: a second map.** Follow [MAP_IMPORT_PLAYBOOK.md](MAP_IMPORT_PLAYBOOK.md): de_dust first, then BSP v19 support (12 stock CS:S maps), texture downsampling and a prop triangle budget.
2. Import player-clip brushes as invisible collision; carry alpha-test/translucency to the runtime.
3. Source lightmaps and common VMT shader properties; HL2 textures from a legitimate client install.
4. Add general asset importer dispatch, model/weapon/humanoid workflows and a provider interface for acquisition. Steam Workshop discovery must use legitimate installed content or officially supported APIs and respect app permissions and licenses.

Workshop research: [Steamworks ISteamUGC](https://partner.steamgames.com/doc/api/isteamugc) is tied to the consumer application's ID and permissions. [Steamworks' implementation guide](https://partner.steamgames.com/doc/features/workshop/implementation) describes game/app enablement. The older `ISteamRemoteStorage` interface is [deprecated for new Workshop integration](https://partner.steamgames.com/doc/api/isteamremotestorage). A standalone third-party app cannot assume Garry's Mod's UGC authorization or direct anonymous download URLs. Local BSP import remains independent of any Workshop provider.
