# Roadmap

1. **Next: test Android exploration on a phone.** The external package picker and basic walking mode now use the imported world mesh, collision and spawn without Trial scenario tags. Measure movement, device memory and GPU behavior on de_dust2.
2. Add Source brush collision and classify invisible clips and non-solid decorative surfaces. Test wall, slope, opening and floor movement on device.
3. Add unpacked game/VPK material resolution, Source lightmaps and common VMT shader properties. Implement static-prop model conversion for maps that need props to be playable.
4. Add general asset importer dispatch, model/weapon/humanoid workflows and a provider interface for acquisition. Steam Workshop discovery must use legitimate installed content or officially supported APIs and respect app permissions and licenses.

Workshop research: [Steamworks ISteamUGC](https://partner.steamgames.com/doc/api/isteamugc) is tied to the consumer application's ID and permissions. [Steamworks' implementation guide](https://partner.steamgames.com/doc/features/workshop/implementation) describes game/app enablement. The older `ISteamRemoteStorage` interface is [deprecated for new Workshop integration](https://partner.steamgames.com/doc/api/isteamremotestorage). A standalone third-party app cannot assume Garry's Mod's UGC authorization or direct anonymous download URLs. Local BSP import remains independent of any Workshop provider.
