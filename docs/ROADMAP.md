# Roadmap

Done 2026-09-23: phone-tested de_dust2 matches (Open Halo sandbox branch), VPK material resolution, static-prop models, non-solid prop flag.

1. **Next: a player model and a weapon** (CS:S terrorist or a GMod character, CS:S AK-47): skinned MDL + animations + a character/weapon package, mapped onto Open Halo's bipeds and weapons through a translation registry. Plan in HANDOFF.md. (Done: de_aztec, cs_office, gm_construct bundled and at 120 fps on the phone.)
2. Import player-clip brushes as invisible collision; carry alpha-test/translucency to the runtime.
3. Source lightmaps and common VMT shader properties; HL2 textures from a legitimate client install.
4. Add general asset importer dispatch, model/weapon/humanoid workflows and a provider interface for acquisition. Steam Workshop discovery must use legitimate installed content or officially supported APIs and respect app permissions and licenses.

Workshop research: [Steamworks ISteamUGC](https://partner.steamgames.com/doc/api/isteamugc) is tied to the consumer application's ID and permissions. [Steamworks' implementation guide](https://partner.steamgames.com/doc/features/workshop/implementation) describes game/app enablement. The older `ISteamRemoteStorage` interface is [deprecated for new Workshop integration](https://partner.steamgames.com/doc/api/isteamremotestorage). A standalone third-party app cannot assume Garry's Mod's UGC authorization or direct anonymous download URLs. Local BSP import remains independent of any Workshop provider.
