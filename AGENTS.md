# Working in Open Asset Lab

- Keep this repository separate from Open Halo. Runtime contract changes must be coordinated and tested in both repositories.
- Never commit BSPs, VMTs, VTFs, VPKs, Workshop downloads, staged packages, previews from proprietary maps, Halo data, tokens or personal paths in generated artifacts.
- Use original in-memory synthetic fixtures for public tests. Keep real maps under a private directory outside either Git repository.
- Run `python -m unittest discover -s tests -v` after importer or package changes. For Open Halo changes run its `scripts/verify.sh` with the owner's existing Trial data.
- Verify a real Source map with Open Halo's `open-halo-map-test` before claiming end-to-end map rendering. A standalone converter output is insufficient.
- Preserve source material paths and warnings. Unsupported features should fail explicitly or appear in the report.
